from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import AnalyticsService
from app.config import Settings
from app.db.models import Insight, Notification, NotificationRecipient, Tenant, TenantHotel
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus
from app.notify.alert_rules import AlertItem
from app.notify.kinds import NotificationKind
from app.notify.service import NotificationService, TenantInfo
from app.repo.snapshots import SnapshotRepository
from tests.fakes import FakeEmailSender
from tests.integration.seed import scan_run
from tests.integration.test_api import _login, _offer, _seed

STAY = date(2026, 10, 5)
NOW = datetime(2026, 10, 1, 2, 0, tzinfo=UTC)  # 09:00 giờ Việt Nam, đêm 05/10 trong 14 đêm tới


def _probe(status: ProbeStatus, offers: tuple = ()) -> ProbeResult:  # type: ignore[type-arg]
    return ProbeResult(
        status,
        ProbeMethod.HTTP,
        STAY,
        STAY + timedelta(days=1),
        1,
        2,
        offers,
        "<html/>",
        200,
        "s",
        10,
    )


async def _competitor_sells_out(
    db: AsyncSession, ids: dict[str, int], channel: str = "booking"
) -> int:
    """Hai lượt quét: đối thủ còn phòng rồi hết phòng đêm STAY. Trả về id lượt thứ hai."""
    repo = SnapshotRepository(db, 10)
    run_id = 0
    for i, status in enumerate((ProbeStatus.OK, ProbeStatus.SOLD_OUT)):
        at = NOW - timedelta(hours=10 - i * 8)
        run = scan_run(
            f"n{i}:{channel}", at, channel=channel, finished_at=at + timedelta(minutes=10)
        )
        run.total_probes = 1
        db.add(run)
        await db.flush()
        offers = (_offer("1", 3, 3, "100"),) if status == ProbeStatus.OK else ()
        await repo.write_probe(
            run.id, ids["comp"], channel, STAY, _probe(status, offers), None, "1", "vn", at
        )
        await db.commit()
        await AnalyticsService(db).run(run.id)
        await db.commit()
        run_id = run.id
    return run_id


async def test_settings_recipients_rules_and_permissions(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")

    r = await client.get("/notifications/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["email_configured"] is True and body["recipients"] == []
    assert {x["kind"] for x in body["rules"]} >= {"daily_insight", "competitor_sold_out"}
    # Mọi loại bật mặc định, trừ "lệch định vị" (cần đặt mục tiêu trong chiến lược giá trước).
    assert all(x["active"] for x in body["rules"] if x["kind"] != "own_position_drift")
    assert not next(x for x in body["rules"] if x["kind"] == "own_position_drift")["active"]

    r = await client.post("/notifications/recipients", json={"email": "Owner@Rex.vn"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    dup = await client.post("/notifications/recipients", json={"email": "owner@rex.vn"})
    assert dup.status_code == 409
    assert (
        await client.post("/notifications/recipients", json={"email": "nope"})
    ).status_code == 422

    r = await client.put(
        "/notifications/rules/competitor_price_drop",
        json={"active": True, "params": {"min_pct": 20}},
    )
    assert r.status_code == 200 and r.json()["params"] == {"within_days": 14, "min_pct": 20}
    bad = await client.put(
        "/notifications/rules/competitor_price_drop",
        json={"active": True, "params": {"min_pct": 0}},
    )
    assert bad.status_code == 422
    assert (
        await client.put("/notifications/rules/unknown", json={"active": True})
    ).status_code == 422
    rules = {x["kind"]: x for x in (await client.get("/notifications/settings")).json()["rules"]}
    assert rules["competitor_price_drop"]["params"]["min_pct"] == 20

    await _login(client, "view@a.com", "view-pass-1")
    assert (await client.get("/notifications/settings")).status_code == 200
    assert (
        await client.post("/notifications/recipients", json={"email": "x@y.vn"})
    ).status_code == 403
    assert (await client.delete(f"/notifications/recipients/{rid}")).status_code == 403

    await _login(client, "admin@a.com", "admin-pass-1")
    assert (await client.delete(f"/notifications/recipients/{rid}")).status_code == 204
    assert (await client.delete(f"/notifications/recipients/{rid}")).status_code == 404


async def test_send_test_email_rate_limited_and_logged(
    client: AsyncClient, db: AsyncSession, email_sender: FakeEmailSender
) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/notifications/test")
    assert r.status_code == 200 and r.json()["status"] == "skipped"
    assert r.json()["reason"] == "no_recipients"

    await client.post("/notifications/recipients", json={"email": "owner@rex.vn"})
    # Lần thử trước đã chiếm khoá của phút này: phải đợi sang phút sau.
    assert (await client.post("/notifications/test")).status_code == 429
    await db.execute(Notification.__table__.delete())
    await db.commit()
    r = await client.post("/notifications/test")
    assert r.status_code == 200 and r.json()["status"] == "sent", r.text
    assert [to for to, _ in email_sender.sent] == ["owner@rex.vn"]
    log = (await client.get("/notifications/log")).json()
    assert log[0]["kind"] == "test" and log[0]["recipients"] == ["owner@rex.vn"]
    assert log[0]["detail"] is None


async def test_dispatch_alerts_once_and_retry_failed(db: AsyncSession, settings: Settings) -> None:
    ids = await _seed(db)
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="owner@rex.vn", active=True))
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="gm@rex.vn", active=True))
    await db.commit()
    run_id = await _competitor_sells_out(db, ids)

    sender = FakeEmailSender()
    sender.fail_for = {"owner@rex.vn", "gm@rex.vn"}
    svc = NotificationService(db, sender, settings)
    report = await svc.dispatch_due(NOW)
    await db.commit()
    assert report.alerts == 0
    row = (
        await db.execute(select(Notification).where(Notification.scan_run_id == run_id))
    ).scalar_one()
    assert row.kind == "alerts" and row.status == "failed" and row.attempts == 1
    assert row.subject == "Comp Hotel hết phòng đêm T2 05/10"

    sender.fail_for = {"gm@rex.vn"}
    report = await svc.dispatch_due(NOW + timedelta(minutes=5))
    await db.commit()
    assert report.retried == 1 and report.alerts == 0  # không chèn lại khoá đã có
    await db.refresh(row)
    assert row.status == "sent" and row.recipients == ["owner@rex.vn"] and row.attempts == 2
    assert [to for to, _ in sender.sent] == ["owner@rex.vn"]

    # Chạy lại nữa: không gửi trùng, không thử lại email đã gửi.
    await svc.dispatch_due(NOW + timedelta(minutes=10))
    await db.commit()
    assert len(sender.sent) == 1
    # Lượt đầu (đối thủ còn phòng) không có gì để báo: ghi "no_matches", không gửi.
    skipped = (
        (await db.execute(select(Notification).where(Notification.status == "skipped")))
        .scalars()
        .all()
    )
    assert [s.detail for s in skipped] == ["no_matches"]


async def test_dispatch_without_smtp_is_logged_not_sent(
    client: AsyncClient, db: AsyncSession, settings: Settings
) -> None:
    ids = await _seed(db)
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="owner@rex.vn", active=True))
    await db.commit()
    run_id = await _competitor_sells_out(db, ids)

    sender = FakeEmailSender(configured=False)
    await NotificationService(db, sender, settings).dispatch_due(NOW)
    await db.commit()
    row = (
        await db.execute(select(Notification).where(Notification.scan_run_id == run_id))
    ).scalar_one()
    assert row.status == "skipped" and row.detail == "smtp_not_configured" and not sender.sent

    await _login(client, "admin@a.com", "admin-pass-1")
    log = (await client.get("/notifications/log")).json()
    assert [x["reason"] for x in log] == ["smtp_not_configured"]


async def test_disabled_rule_sends_nothing(db: AsyncSession, settings: Settings) -> None:
    ids = await _seed(db)
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="owner@rex.vn", active=True))
    await db.commit()
    run_id = await _competitor_sells_out(db, ids)
    sender = FakeEmailSender()
    svc = NotificationService(db, sender, settings)
    await svc.mark_rule(
        ids["t1"],
        NotificationKind.COMPETITOR_SOLD_OUT,
        False,
        {"within_days": 14, "min_sold_out": 1},
    )
    await db.commit()
    await svc.dispatch_due(NOW)
    await db.commit()
    row = (
        await db.execute(select(Notification).where(Notification.scan_run_id == run_id))
    ).scalar_one()
    assert row.status == "skipped" and row.detail == "no_matches" and not sender.sent


async def test_daily_insight_email_sent_once(db: AsyncSession, settings: Settings) -> None:
    ids = await _seed(db)
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="owner@rex.vn", active=True))
    insight = Insight(
        tenant_id=ids["t1"],
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 30),
        generated_at=NOW - timedelta(hours=1),
        trigger="daily",
        status="completed",
        model="m",
        prompt_version="v",
        input_json={},
        output_json={"summary": "Cuối tuần đối thủ kín phòng. Thêm chi tiết.", "highlights": []},
    )
    on_demand = Insight(
        tenant_id=ids["t1"],
        period_start=date(2026, 10, 1),
        period_end=date(2026, 10, 30),
        generated_at=NOW - timedelta(hours=1),
        trigger="on_demand",
        status="completed",
        model="m",
        prompt_version="v",
        input_json={},
        output_json={"summary": "x"},
    )
    db.add_all([insight, on_demand])
    await db.commit()
    sender = FakeEmailSender()
    svc = NotificationService(db, sender, settings)
    assert (await svc.dispatch_due(NOW)).insights == 1
    await db.commit()
    assert (await svc.dispatch_due(NOW)).insights == 0
    assert [e.subject for _, e in sender.sent] == [
        "Bản tin sáng 01/10: Cuối tuần đối thủ kín phòng"
    ]


async def test_weekly_report_monday_morning_once(db: AsyncSession, settings: Settings) -> None:
    ids = await _seed(db)
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="owner@rex.vn", active=True))
    await db.commit()
    await _competitor_sells_out(db, ids)

    sender = FakeEmailSender()
    svc = NotificationService(db, sender, settings)
    sunday = datetime(2026, 10, 4, 3, 0, tzinfo=UTC)
    assert (await svc.dispatch_weekly(sunday)) == 0
    monday = datetime(2026, 10, 5, 1, 30, tzinfo=UTC)  # 08:30 thứ Hai giờ Việt Nam
    assert (await svc.dispatch_weekly(monday)) == 1
    await db.commit()
    assert (await svc.dispatch_weekly(monday + timedelta(hours=3))) == 0
    subjects = [e.subject for _, e in sender.sent]
    assert subjects == ["Báo cáo tuần 05/10: 1 đêm tới quá nửa đối thủ hết phòng"]
    assert "Comp Hotel" in sender.sent[0][1].text


async def test_retry_backoff_atomic_claim_and_tests_not_retried(
    db: AsyncSession, settings: Settings
) -> None:
    ids = await _seed(db)
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="owner@rex.vn", active=True))
    await db.commit()
    run_id = await _competitor_sells_out(db, ids)
    sender = FakeEmailSender()
    sender.fail_for = {"owner@rex.vn"}
    svc = NotificationService(db, sender, settings)
    await svc.dispatch_due(NOW)
    row = (
        await db.execute(select(Notification).where(Notification.scan_run_id == run_id))
    ).scalar_one()
    assert row.status == "failed" and row.attempts == 1

    # Chưa hết thời gian chờ sau lần lỗi đầu (5 phút): không thử lại.
    assert (await svc.retry(NOW + timedelta(minutes=2))) == 0
    # Hai lần cron chồng nhau cùng thấy (failed, attempts=1): chỉ một bên giành được dòng.
    later = NOW + timedelta(minutes=6)
    assert await svc._retry_one(row.id, "failed", 1, later) == 1
    assert await svc._retry_one(row.id, "failed", 1, later) == 0
    await db.refresh(row)
    assert row.attempts == 2 and row.status == "failed"
    # Lần lỗi thứ hai phải chờ 30 phút.
    assert (await svc.retry(later + timedelta(minutes=10))) == 0
    assert (await svc.retry(later + timedelta(minutes=31))) == 1

    # Email thử lỗi không bị cron gửi lại.
    test_row = await svc.send_test(await db.get(Tenant, ids["t1"]), NOW)  # type: ignore[arg-type]
    assert test_row.status == "failed"
    await svc.retry(NOW + timedelta(hours=3))
    await db.refresh(test_row)
    assert test_row.attempts == 1


async def test_one_failing_tenant_does_not_block_others(
    db: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = await _seed(db)
    # Tenant 2 theo dõi cùng đối thủ để lượt quét có hai tenant.
    db.add(TenantHotel(tenant_id=ids["t2"], hotel_id=ids["comp"], role="competitor", active=True))
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="a@rex.vn", active=True))
    db.add(NotificationRecipient(tenant_id=ids["t2"], email="b@other.vn", active=True))
    await db.commit()
    await _competitor_sells_out(db, ids)
    svc = NotificationService(db, FakeEmailSender(), settings)
    original = svc.alerts_for_run

    async def boom(tenant: TenantInfo, run_id: int, now: datetime) -> list[AlertItem]:
        if tenant.id == ids["t1"]:
            raise RuntimeError("bad data")
        return await original(tenant, run_id, now)

    monkeypatch.setattr(svc, "alerts_for_run", boom)
    report = await svc.dispatch_due(NOW)
    assert report.alerts == 1  # tenant 2 vẫn nhận
    sent_to = [to for to, _ in svc._sender.sent]  # type: ignore[attr-defined]
    assert sent_to == ["b@other.vn"]


async def test_hotel_name_with_newline_still_sends(db: AsyncSession, settings: Settings) -> None:
    ids = await _seed(db)
    link = (
        await db.execute(
            select(TenantHotel).where(
                TenantHotel.tenant_id == ids["t1"], TenantHotel.hotel_id == ids["comp"]
            )
        )
    ).scalar_one()
    link.label = "Comp\r\nBcc: x@evil.vn " + "A" * 90
    db.add(NotificationRecipient(tenant_id=ids["t1"], email="owner@rex.vn", active=True))
    await db.commit()
    await _competitor_sells_out(db, ids)
    sender = FakeEmailSender()
    await NotificationService(db, sender, settings).dispatch_due(NOW)
    ((_, email),) = sender.sent
    assert "\n" not in email.subject and "\r" not in email.subject and len(email.subject) <= 200
