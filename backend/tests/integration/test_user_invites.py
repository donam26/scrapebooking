"""Mời người dùng qua link đặt mật khẩu, lần đăng nhập cuối, người nhập PMS (UX Phase 3, C5;
migration 0021)."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from alembic import command
from alembic.config import Config
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.models import User
from tests.fakes import FakeEmailSender
from tests.integration.test_api import _login, _seed

DAILY_CSV = "Ngày,Phòng đã bán,Tổng phòng\n10/10/2026,167,286\n".encode()
OTB_CSV = "Ngày ở,Phòng đã đặt\n20/10/2026,42\n".encode()


def _token(invite_url: str) -> str:
    return parse_qs(urlparse(invite_url).query)["token"][0]


async def _user(client: AsyncClient, email: str) -> dict:  # type: ignore[type-arg]
    users = (await client.get("/users")).json()
    return next(u for u in users if u["email"] == email)


async def test_invite_set_password_then_login(
    client: AsyncClient, db: AsyncSession, email_sender: FakeEmailSender
) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/users/invite", json={"email": "New@Rex.vn", "role": "viewer"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email_status"] == "sent"
    assert body["invite_url"].startswith("http://localhost:3000/set-password?token=")
    assert body["user"]["email"] == "new@rex.vn" and body["user"]["tenant_id"] == ids["t1"]
    assert body["user"]["invite_pending"] is True and body["user"]["last_login_at"] is None
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=71) < expires - datetime.now(tz=UTC) <= timedelta(hours=72)
    # Email theo ngôn ngữ báo cáo của tenant, có link, không có chữ kỹ thuật.
    to, email = email_sender.sent[-1]
    assert to == "new@rex.vn"
    assert email.subject == "A mời bạn dùng OTARadar"
    assert body["invite_url"] in email.text and "chỉ xem" in email.text
    assert "token" not in email.text.replace(body["invite_url"], "")

    listed = await _user(client, "new@rex.vn")
    assert listed["invite_pending"] is True and listed["invite_expires_at"] is not None

    # Chưa đặt mật khẩu: đăng nhập bị từ chối với mọi mật khẩu.
    stored = (await db.execute(select(User).where(User.email == "new@rex.vn"))).scalar_one()
    for guess in ("", "x" * 8, stored.password_hash):
        r = await client.post("/auth/login", json={"email": "new@rex.vn", "password": guess or "?"})
        assert r.status_code == 401
    token = _token(body["invite_url"])
    secret = token.split(".", 1)[1]
    # DB chỉ giữ hash của phần bí mật.
    assert stored.invite_token_hash is not None and len(stored.invite_token_hash) == 64
    assert secret not in (stored.invite_token_hash, stored.password_hash)

    r = await client.post("/auth/set-password", json={"token": token, "password": "short"})
    assert r.status_code == 422
    r = await client.post("/auth/set-password", json={"token": token, "password": "new-pass-123"})
    assert r.status_code == 204, r.text
    # Dùng một lần.
    r = await client.post("/auth/set-password", json={"token": token, "password": "other-pass-1"})
    assert (r.status_code, r.json()["detail"]) == (400, "invalid invite token")

    r = await client.post("/auth/login", json={"email": "new@rex.vn", "password": "new-pass-123"})
    assert r.status_code == 200
    assert r.json()["role"] == "viewer" and r.json()["last_login_at"] is not None
    await _login(client, "admin@a.com", "admin-pass-1")
    listed = await _user(client, "new@rex.vn")
    assert listed["invite_pending"] is False and listed["invite_expires_at"] is None
    assert listed["last_login_at"] is not None


async def test_invite_without_email_channel_returns_link_and_failed_send(
    client: AsyncClient, db: AsyncSession, email_sender: FakeEmailSender
) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    email_sender.configured = False
    r = await client.post("/users/invite", json={"email": "a1@rex.vn", "role": "viewer"})
    assert r.json()["email_status"] == "not_configured" and "token=" in r.json()["invite_url"]
    assert email_sender.sent == []

    email_sender.configured = True
    email_sender.fail_for.add("a2@rex.vn")
    r = await client.post("/users/invite", json={"email": "a2@rex.vn", "role": "tenant_admin"})
    assert r.status_code == 201 and r.json()["email_status"] == "failed"


async def test_expired_token_and_bad_tokens(client: AsyncClient, db: AsyncSession) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/users/invite", json={"email": "late@rex.vn", "role": "viewer"})
    token = _token(r.json()["invite_url"])
    await db.execute(
        text("update users set invite_expires_at = now() - interval '1 minute' where email = :e"),
        {"e": "late@rex.vn"},
    )
    await db.commit()
    r = await client.post("/auth/set-password", json={"token": token, "password": "late-pass-1"})
    assert (r.status_code, r.json()["detail"]) == (410, "invite token expired")

    uid = token.split(".")[0]
    for bad in ("nope", f"{uid}.wrong-secret", f"999999.{token.split('.')[1]}", f".{token}"):
        r = await client.post("/auth/set-password", json={"token": bad, "password": "late-pass-1"})
        assert (r.status_code, r.json()["detail"]) == (400, "invalid invite token"), bad


async def test_resend_invalidates_old_token(
    client: AsyncClient, db: AsyncSession, email_sender: FakeEmailSender
) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    first = (
        await client.post("/users/invite", json={"email": "again@rex.vn", "role": "viewer"})
    ).json()
    uid = first["user"]["id"]
    r = await client.post(f"/users/{uid}/invite")
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["invite_url"] != first["invite_url"] and len(email_sender.sent) == 2

    old, new = _token(first["invite_url"]), _token(second["invite_url"])
    r = await client.post("/auth/set-password", json={"token": old, "password": "again-pass-1"})
    assert r.status_code == 400
    r = await client.post("/auth/set-password", json={"token": new, "password": "again-pass-1"})
    assert r.status_code == 204
    r = await client.post(f"/users/{uid}/invite")
    assert (r.status_code, r.json()["detail"]) == (409, "user already has a password")


async def test_invite_permissions_and_admin_password_cancels_invite(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    await _login(client, "view@a.com", "view-pass-1")
    r = await client.post("/users/invite", json={"email": "x@rex.vn", "role": "viewer"})
    assert r.status_code == 403

    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post("/users/invite", json={"email": "x@rex.vn", "role": "operator"})
    assert (r.status_code, r.json()["detail"]) == (403, "operator only")
    r = await client.post("/users/invite", json={"email": "view@a.com", "role": "viewer"})
    assert (r.status_code, r.json()["detail"]) == (409, "email already exists")
    # tenant_admin không chọn được tenant khác: luôn vào tenant của mình.
    r = await client.post(
        "/users/invite", json={"email": "x@rex.vn", "role": "viewer", "tenant_id": ids["t2"]}
    )
    assert r.json()["user"]["tenant_id"] == ids["t1"]
    token, uid = _token(r.json()["invite_url"]), r.json()["user"]["id"]
    # Quản trị đặt mật khẩu thay: link mời mất hiệu lực, hết trạng thái chờ.
    r = await client.patch(f"/users/{uid}", json={"password": "admin-set-1"})
    assert r.status_code == 200 and r.json()["invite_pending"] is False
    r = await client.post("/auth/set-password", json={"token": token, "password": "mine-pass-1"})
    assert r.status_code == 400

    await _login(client, "op@x.com", "op-pass-123")
    r = await client.post(
        "/users/invite", json={"email": "b@other.vn", "role": "viewer", "tenant_id": ids["t2"]}
    )
    other = r.json()["user"]["id"]
    await _login(client, "admin@a.com", "admin-pass-1")
    assert (await client.post(f"/users/{other}/invite")).status_code == 404

    # Tài khoản bị khoá: link không dùng được, không gửi lại được.
    r = await client.post("/users/invite", json={"email": "lock@rex.vn", "role": "viewer"})
    token, uid = _token(r.json()["invite_url"]), r.json()["user"]["id"]
    await client.patch(f"/users/{uid}", json={"active": False})
    r = await client.post("/auth/set-password", json={"token": token, "password": "lock-pass-1"})
    assert r.status_code == 400
    assert (await client.post(f"/users/{uid}/invite")).status_code == 409


async def test_pms_and_otb_imports_record_who_imported(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post(
        "/pms/import",
        files={"file": ("ez.csv", DAILY_CSV, "text/csv")},
        data={"hotel_id": str(ids["own"])},
    )
    assert r.status_code == 201 and r.json()["created_by_email"] == "admin@a.com"
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.post(
        f"/pms/otb/import?tenant_id={ids['t1']}",
        files={"file": ("otb.csv", OTB_CSV, "text/csv")},
        data={"hotel_id": str(ids["own"]), "kind": "otb_report"},
    )
    assert r.status_code == 201, r.text
    await _login(client, "admin@a.com", "admin-pass-1")
    imports = (await client.get("/pms/imports")).json()
    assert [(i["filename"], i["created_by_email"]) for i in imports] == [
        ("otb.csv", "op@x.com"),
        ("ez.csv", "admin@a.com"),
    ]
    # Xoá tài khoản: lịch sử nhập giữ lại, người nhập thành trống.
    await db.execute(text("delete from users where email = 'op@x.com'"))
    await db.commit()
    imports = (await client.get("/pms/imports")).json()
    assert [i["created_by_email"] for i in imports] == [None, "admin@a.com"]


async def test_migration_0021_round_trip(db: AsyncSession, migrated_db_url: str) -> None:
    await db.close()
    await db.bind.dispose()  # type: ignore[union-attr]
    cfg = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", migrated_db_url)

    async def columns() -> set[tuple[str, str]]:
        engine = create_async_engine(migrated_db_url)
        try:
            async with engine.connect() as conn:
                rows = await conn.execute(
                    text(
                        "select table_name, column_name from information_schema.columns "
                        "where table_name in ('users', 'pms_imports')"
                    )
                )
                return {(r[0], r[1]) for r in rows}
        finally:
            await engine.dispose()

    added = {
        ("users", "last_login_at"),
        ("users", "invite_token_hash"),
        ("users", "invite_expires_at"),
        ("pms_imports", "created_by"),
    }
    try:
        await asyncio.to_thread(command.downgrade, cfg, "0020")
        assert not (added & await columns())
    finally:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    assert added <= await columns()
