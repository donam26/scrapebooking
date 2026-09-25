"""Các ràng buộc phát hiện khi rà soát flow người dùng: múi giờ, tự khoá, operator cuối,
bản tin pending treo, tài khoản bị khoá mất hiệu lực ngay, ánh xạ PMS theo tệp."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.pms import effective_mapping
from app.db.models import Insight, User
from tests.integration.test_api import _login, _seed


async def test_invalid_timezone_rejected_and_country_lowercased(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.patch("/settings", json={"timezone": "Mars/Olympus"})
    assert r.status_code == 422 and "timezone" in r.json()["detail"]
    r = await client.patch("/settings", json={"timezone": "Asia/Bangkok", "country_code": "TH"})
    assert r.status_code == 200 and r.json()["timezone"] == "Asia/Bangkok"
    assert r.json()["country_code"] == "th"
    r = await client.patch("/settings", json={"scan_times": []})
    assert r.status_code == 422
    r = await client.patch("/settings", json={"scan_times": ["14:00", "06:00", "06:00"]})
    assert r.status_code == 200 and r.json()["scan_times"] == ["06:00", "14:00"]
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.post("/tenants", json={"name": "Bad", "timezone": "Nope/Nope"})
    assert r.status_code == 422


async def test_scan_times_limited_to_eight(client: AsyncClient, db: AsyncSession) -> None:
    # Tài liệu và UI: 1–8 mốc giờ quét mỗi ngày; API cũng phải chặn.
    await _seed(db)
    nine = [f"{h:02d}:00" for h in range(9)]
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.patch("/settings", json={"scan_times": nine})
    assert r.status_code == 422, r.text
    r = await client.patch("/settings", json={"scan_times": nine[:8]})
    assert r.status_code == 200 and len(r.json()["scan_times"]) == 8
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.post("/tenants", json={"name": "N", "scan_times": nine})
    assert r.status_code == 422, r.text


async def test_cannot_lock_self_or_last_operator(client: AsyncClient, db: AsyncSession) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    me = (await client.get("/auth/me")).json()
    r = await client.patch(f"/users/{me['id']}", json={"active": False})
    assert r.status_code == 422
    r = await client.patch(f"/users/{me['id']}", json={"role": "viewer"})
    assert r.status_code == 422
    r = await client.patch(f"/users/{me['id']}", json={"password": "another-pass-1"})
    assert r.status_code == 200
    await _login(client, "admin@a.com", "another-pass-1")

    await _login(client, "op@x.com", "op-pass-123")
    op = (await client.get("/auth/me")).json()
    r = await client.post(
        "/users", json={"email": "op2@x.com", "password": "op2-pass-123", "role": "operator"}
    )
    assert r.status_code == 201
    op2 = r.json()["id"]
    r = await client.patch(f"/users/{op2}", json={"active": False})
    assert r.status_code == 200  # còn op1 hoạt động
    r = await client.patch(f"/users/{op['id']}", json={"active": False})
    assert r.status_code == 422  # tự khoá
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.patch(f"/users/{op2}", json={"active": True})
    assert r.status_code == 200
    # op2 là operator khác đang hoạt động: op1 có thể bị op2 hạ vai trò? Không: op2 chưa đăng nhập,
    # kiểm tra "operator cuối" khi hạ op2 sau khi khoá op1 là không xảy ra vì op1 không tự khoá được.


async def test_disabled_user_loses_access_immediately(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed(db)
    await _login(client, "view@a.com", "view-pass-1")
    assert (await client.get("/watchlist")).status_code == 200
    viewer = (await db.execute(select(User).where(User.email == "view@a.com"))).scalar_one()
    viewer.active = False
    await db.commit()
    r = await client.get("/watchlist")
    assert r.status_code == 401


async def test_role_change_takes_effect_without_relogin(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed(db)
    await _login(client, "view@a.com", "view-pass-1")
    r = await client.post(
        "/watchlist", json={"booking_url": "https://www.booking.com/hotel/vn/x.html"}
    )
    assert r.status_code == 403
    viewer = (await db.execute(select(User).where(User.email == "view@a.com"))).scalar_one()
    viewer.role = "tenant_admin"
    await db.commit()
    r = await client.post(
        "/watchlist", json={"booking_url": "https://www.booking.com/hotel/vn/x.html"}
    )
    assert r.status_code == 201


async def test_stale_pending_insight_marked_failed(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    old = Insight(
        tenant_id=ids["t1"],
        period_start=datetime.now(tz=UTC).date(),
        period_end=datetime.now(tz=UTC).date(),
        generated_at=datetime.now(tz=UTC) - timedelta(minutes=30),
        trigger="on_demand",
        status="pending",
        model="m",
        prompt_version="1",
        input_json={},
        output_json=None,
        dropped_highlights=[],
    )
    db.add(old)
    await db.commit()
    old_id = old.id
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/insights/generate")
    assert r.status_code == 202 and r.json()["id"] != old_id
    db.expire_all()
    stale = await db.get(Insight, old_id)
    assert stale is not None and stale.status == "failed" and "timeout" in (stale.error or "")


def test_effective_mapping_prefers_stored_only_when_column_exists() -> None:
    stored = {"stay_date": "Ngày", "rooms_total": "Tổng phòng", "adr": "ADR"}
    suggested = {"stay_date": "Date", "rooms_sold": "Sold"}
    columns = ["Date", "Sold", "ADR"]
    assert effective_mapping(stored, suggested, columns) == {
        "stay_date": "Date",
        "rooms_sold": "Sold",
        "adr": "ADR",
    }
    assert effective_mapping({}, suggested, columns) == suggested


async def test_preview_uses_file_columns_over_stale_mapping(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.put(
        "/pms/mapping",
        json={"adapter": "csv", "mapping": {"stay_date": "Ngày", "rooms_total": "Tổng phòng"}},
    )
    assert r.status_code == 200
    csv_bytes = b"Date,Rooms,Sold\n2026-10-01,100,80\n"
    r = await client.post("/pms/preview", files={"file": ("other.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["suggested_mapping"] == {
        "stay_date": "Date",
        "rooms_total": "Rooms",
        "rooms_sold": "Sold",
    }
    assert r.json()["parsed_ok"] == 1
    r = await client.post(
        "/pms/preview",
        files={
            "file": ("old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1junk", "application/vnd.ms-excel")
        },
    )
    assert r.status_code == 422 and ".xlsx" in r.json()["detail"]
