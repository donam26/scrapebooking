"""UX Phase 3: thẻ "Thiết lập 5 bước", tự nhận loại tệp PMS, gộp người nhận (migration 0019)."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.models import NotificationSubscription, PmsImport, TenantHotel
from app.market.models import PriceStrategy
from tests.integration.seed import add_hotel
from tests.integration.test_api import _login, _seed

DAILY_CSV = (
    "Ngày,Phòng đã bán,Tổng phòng,Doanh thu\n"
    "10/10/2026,167,286,567800000\n"
    "11/10/2026,222,286,754800000\n"
).encode()
OTB_CSV = (
    b"Ng\xc3\xa0y \xe1\xbb\x9f,Ph\xc3\xb2ng \xc4\x91\xc3\xa3 \xc4\x91\xe1\xba\xb7t\n20/10/2026,42\n"
)


async def test_setup_steps_dismiss_and_viewer_cannot_dismiss(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    s = (await client.get("/settings/setup")).json()
    assert (s["own_hotel"], s["competitors"], s["competitors_needed"]) == (True, 1, 4)
    assert (s["strategy"], s["alerts"], s["pms"], s["done"]) == (False, False, False, False)
    assert s["dismissed_at"] is None and s["balance"] is None  # chưa có giá để so

    for i in range(3):
        h = await add_hotel(db, f"vn/comp-{i}", name=f"Comp {i}")
        db.add(TenantHotel(tenant_id=ids["t1"], hotel_id=h.id, role="competitor", active=True))
    db.add(PriceStrategy(tenant_id=ids["t1"], hotel_id=ids["own"], target_index=95))
    db.add(NotificationSubscription(tenant_id=ids["t1"], channel="email", target="gm@rex.vn"))
    db.add(
        PmsImport(
            tenant_id=ids["t1"],
            hotel_id=ids["own"],
            filename="x.csv",
            adapter="csv",
            row_count=1,
            ok_count=1,
            errors=[],
            status="ok",
        )
    )
    await db.commit()
    s = (await client.get("/settings/setup")).json()
    assert (s["competitors"], s["strategy"], s["alerts"], s["pms"], s["done"]) == (
        4,
        True,
        True,
        True,
        True,
    )

    r = await client.put("/settings/setup", json={"dismissed": True})
    assert r.status_code == 200 and r.json()["dismissed_at"] is not None
    assert (await client.get("/settings/setup")).json()["dismissed_at"] is not None
    await _login(client, "view@a.com", "view-pass-1")
    assert (await client.get("/settings/setup")).status_code == 200
    assert (await client.put("/settings/setup", json={"dismissed": False})).status_code == 403
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.put("/settings/setup", json={"dismissed": False})
    assert r.json()["dismissed_at"] is None


async def test_pms_preview_detects_file_kind_and_import_reports_range(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/pms/preview", files={"file": ("ez.csv", DAILY_CSV, "text/csv")})
    body = r.json()
    assert (body["kind"], body["detected_kind"], body["missing"]) == ("daily", "daily", [])
    assert body["parsed_ok"] == 2

    r = await client.post("/pms/preview", files={"file": ("otb.csv", OTB_CSV, "text/csv")})
    body = r.json()
    assert (body["kind"], body["detected_kind"], body["parsed_ok"]) == ("otb_report",) * 2 + (1,)
    # Người dùng đổi loại: đọc lại theo loại đã chọn, báo cột bắt buộc còn thiếu.
    r = await client.post(
        "/pms/preview",
        files={"file": ("otb.csv", OTB_CSV, "text/csv")},
        data={"kind": "bookings"},
    )
    body = r.json()
    assert body["kind"] == "bookings" and body["detected_kind"] == "otb_report"
    assert body["missing"] == ["arrival", "departure", "booking_date"]

    r = await client.post(
        "/pms/import",
        files={"file": ("ez.csv", DAILY_CSV, "text/csv")},
        data={"hotel_id": str(ids["own"])},
    )
    assert r.status_code == 201, r.text
    assert (r.json()["stay_from"], r.json()["stay_to"]) == ("2026-10-10", "2026-10-11")


async def test_recipients_migration_round_trip(db: AsyncSession, migrated_db_url: str) -> None:
    """0019: người nhận email cũ thành đăng ký nhận mọi loại tin; xuống 0018 trả lại người nhận."""
    ids = await _seed(db)
    db.add(
        NotificationSubscription(
            tenant_id=ids["t1"], user_id=None, channel="email", target="gm@rex.vn", kinds=[]
        )
    )
    await db.commit()
    await db.close()
    await db.bind.dispose()  # type: ignore[union-attr]
    cfg = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", migrated_db_url)

    await asyncio.to_thread(command.downgrade, cfg, "0018")
    engine = create_async_engine(migrated_db_url)
    try:
        async with engine.begin() as conn:
            got = (await conn.execute(text("select email from notification_recipients"))).all()
            assert [r[0] for r in got] == ["gm@rex.vn"]
            assert (
                await conn.execute(text("select count(*) from notification_subscriptions"))
            ).scalar_one() == 0
            await conn.execute(
                text(
                    "insert into notification_recipients (tenant_id, email, active) "
                    "values (:t, 'owner@rex.vn', true)"
                ),
                {"t": ids["t1"]},
            )
    finally:
        await engine.dispose()
        await asyncio.to_thread(command.upgrade, cfg, "head")

    engine = create_async_engine(migrated_db_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "select target, kinds, active, user_id, quiet_start "
                        "from notification_subscriptions order by target"
                    )
                )
            ).all()
            setup = (await conn.execute(text("select setup_state from tenants"))).scalars().all()
    finally:
        await engine.dispose()
    kinds = ["alerts", "daily_insight", "weekly_report", "data_stale"]
    assert [tuple(r) for r in rows] == [
        ("gm@rex.vn", kinds, True, None, None),
        ("owner@rex.vn", kinds, True, None, None),
    ]
    assert setup == [{}, {}]
