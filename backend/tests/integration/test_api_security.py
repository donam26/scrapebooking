"""Phase 2: guard cấu hình production, chống dò mật khẩu, thu hồi phiên, CSRF, tenant bị tắt,
quên/đặt lại mật khẩu, listing dùng chung, hạn mức, /metrics, /healthz."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.main import InsecureConfiguration, check_production_settings, create_app
from app.config import Settings
from app.db.models import AuditEvent, Listing, Tenant, TenantHotel, User
from tests.fakes import FakeEmailSender
from tests.integration.conftest import FakeQueue
from tests.integration.test_api import _login, _seed


def _settings(**overrides: object) -> Settings:
    base = dict(
        _env_file=None,
        database_url="x",
        redis_url="x",
        proxy_url_template="x",
        jwt_secret="a-sufficiently-long-random-secret-string-123456",
        cookie_secure=True,
        app_base_url="https://radar.example.vn",
        cors_origins="https://radar.example.vn",
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_production_guard_rejects_default_secret_and_insecure_cookie() -> None:
    check_production_settings(_settings(app_env="prod"))  # cấu hình đủ an toàn: không ném
    with pytest.raises(InsecureConfiguration, match="JWT_SECRET"):
        check_production_settings(_settings(app_env="prod", jwt_secret="change-me"))
    with pytest.raises(InsecureConfiguration, match="COOKIE_SECURE"):
        check_production_settings(_settings(app_env="prod", cookie_secure=False))
    with pytest.raises(InsecureConfiguration, match="CORS"):
        check_production_settings(_settings(app_env="prod", cors_origins="*"))
    # dev: không bắt buộc
    check_production_settings(_settings(app_env="dev", jwt_secret="change-me"))


async def test_login_is_rate_limited_per_email(client: AsyncClient, db: AsyncSession) -> None:
    await _seed(db)
    for _ in range(5):
        r = await client.post("/auth/login", json={"email": "admin@a.com", "password": "nope"})
        assert r.status_code == 401
    r = await client.post("/auth/login", json={"email": "admin@a.com", "password": "nope"})
    assert r.status_code == 429 and r.headers.get("retry-after") == "60"
    # Email không tồn tại cũng 401 (không lộ), và được ghi nhật ký thất bại.
    r = await client.post("/auth/login", json={"email": "ghost@a.com", "password": "nope"})
    assert r.status_code == 401
    failed = (
        (await db.execute(select(AuditEvent).where(AuditEvent.action == "auth.login_failed")))
        .scalars()
        .all()
    )
    assert len(failed) >= 6


async def test_password_change_revokes_other_sessions(
    client: AsyncClient, db: AsyncSession, settings: Settings, queue: FakeQueue
) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    old_cookie = client.cookies.get("sb_session")
    assert old_cookie
    # Thiết bị thứ hai dùng cùng cookie cũ.
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    app = create_app(settings=settings, session_factory=factory, queue=queue)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
            other.cookies.set("sb_session", old_cookie)
            assert (await other.get("/auth/me")).status_code == 200
            r = await client.post(
                "/auth/change-password",
                json={"current_password": "wrong", "new_password": "new-pass-12345"},
            )
            assert r.status_code == 403
            r = await client.post(
                "/auth/change-password",
                json={"current_password": "admin-pass-1", "new_password": "new-pass-12345"},
            )
            assert r.status_code == 200
            # Phiên đổi mật khẩu được cấp cookie mới và vẫn dùng được; cookie cũ bị thu hồi.
            assert (await client.get("/auth/me")).status_code == 200
            assert (await other.get("/auth/me")).status_code == 401
    await _login(client, "admin@a.com", "new-pass-12345")
    r = await client.post("/auth/logout-all")
    assert r.status_code == 204
    assert (await client.get("/auth/me")).status_code == 401


async def test_disabled_tenant_locks_its_users_out(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    assert (await client.get("/settings")).status_code == 200
    await db.execute(update(Tenant).where(Tenant.id == ids["t1"]).values(active=False))
    await db.commit()
    assert (await client.get("/settings")).status_code == 403
    r = await client.post("/auth/login", json={"email": "admin@a.com", "password": "admin-pass-1"})
    assert r.status_code == 403


async def test_csrf_origin_check_blocks_cross_site_writes(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    bad = {"Origin": "https://evil.example"}
    r = await client.patch("/settings", json={"name": "X"}, headers=bad)
    assert r.status_code == 403 and "csrf" in r.json()["detail"]
    r = await client.patch(
        "/settings", json={"name": "X"}, headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert r.status_code == 403
    # Origin của dashboard (APP_BASE_URL / CORS_ORIGINS) và request không có Origin (CLI) đi qua.
    ok = {"Origin": "http://localhost:3000"}
    assert (await client.patch("/settings", json={"name": "Y"}, headers=ok)).status_code == 200
    assert (await client.patch("/settings", json={"name": "Z"})).status_code == 200
    # GET không bị kiểm.
    assert (await client.get("/settings", headers=bad)).status_code == 200


async def test_forgot_and_reset_password_flow(
    client: AsyncClient, db: AsyncSession, email_sender: FakeEmailSender
) -> None:
    await _seed(db)
    # Email lạ: vẫn 204, không gửi gì.
    r = await client.post("/auth/forgot", json={"email": "nobody@a.com"})
    assert r.status_code == 204 and email_sender.sent == []
    r = await client.post("/auth/forgot", json={"email": "admin@a.com"})
    assert r.status_code == 204 and len(email_sender.sent) == 1
    to, email = email_sender.sent[0]
    assert to == "admin@a.com" and "/reset?token=" in email.text
    token = email.text.split("/reset?token=", 1)[1].split()[0]
    r = await client.post("/auth/reset", json={"token": "x" * 32, "password": "whatever-123"})
    assert r.status_code == 400
    r = await client.post("/auth/reset", json={"token": token, "password": "reset-pass-123"})
    assert r.status_code == 204
    # Token dùng một lần.
    r = await client.post("/auth/reset", json={"token": token, "password": "another-pass-1"})
    assert r.status_code == 400
    await _login(client, "admin@a.com", "reset-pass-123")


async def test_shared_listing_cannot_be_repointed_by_one_of_many_tenants(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    comp = ids["comp"]
    # Tenant B cũng theo dõi khách sạn đối thủ của A.
    db.add(TenantHotel(tenant_id=ids["t2"], hotel_id=comp, role="competitor", active=True))
    listing = (
        await db.execute(
            select(Listing).where(Listing.hotel_id == comp, Listing.channel == "booking")
        )
    ).scalar_one()
    listing.status = "broken"
    await db.commit()
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.post(
        f"/watchlist/{comp}/listings",
        json={"url": "https://www.booking.com/hotel/vn/some-other-hotel.html"},
    )
    assert r.status_code == 403, r.text
    r = await client.patch(f"/watchlist/{comp}/listings/{listing.id}", json={"action": "retry"})
    assert r.status_code == 403
    # Operator được phép.
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.patch(
        f"/watchlist/{comp}/listings/{listing.id}?tenant_id={ids['t1']}",
        json={"action": "retry"},
    )
    assert r.status_code == 200 and r.json()["status"] == "unverified"


async def test_listing_error_is_masked_for_tenant_users(
    client: AsyncClient, db: AsyncSession
) -> None:
    ids = await _seed(db)
    listing = (
        await db.execute(
            select(Listing).where(Listing.hotel_id == ids["comp"], Listing.channel == "booking")
        )
    ).scalar_one()
    listing.last_error = "transport: ProxyError: 407 Proxy Authentication Required at 10.0.0.1"
    await db.commit()
    await _login(client, "admin@a.com", "admin-pass-1")
    items = (await client.get("/watchlist")).json()
    errors = [
        ls["last_error"] for it in items for ls in it["hotel"]["listings"] if ls["last_error"]
    ]
    assert errors == ["error"]
    await _login(client, "op@x.com", "op-pass-123")
    items = (await client.get(f"/watchlist?tenant_id={ids['t1']}")).json()
    errors = [
        ls["last_error"] for it in items for ls in it["hotel"]["listings"] if ls["last_error"]
    ]
    assert errors and "407" in errors[0]


async def test_quota_max_hotels_and_manual_scans(
    client: AsyncClient, db: AsyncSession, queue: FakeQueue
) -> None:
    ids = await _seed(db)
    await db.execute(
        update(Tenant)
        .where(Tenant.id == ids["t1"])
        .values(limits={"max_hotels": 2, "manual_scans_per_day": 1})
    )
    await db.commit()
    await _login(client, "admin@a.com", "admin-pass-1")
    # Tenant A đã theo dõi 2 khách sạn (own + comp): thêm khách sạn thứ ba bị chặn.
    r = await client.post(
        "/watchlist",
        json={"url": "https://www.booking.com/hotel/vn/third-hotel.html", "role": "competitor"},
    )
    assert r.status_code == 429 and "quota" in r.json()["detail"]
    r = await client.post("/watchlist/scan-now")
    assert r.status_code == 202, r.text
    r = await client.post("/watchlist/scan-now")  # trong 10 phút: trả run đang chạy, không đếm
    assert r.status_code == 202
    # Giả lập run cũ hơn 10 phút nhưng trong ngày: lần bấm thứ hai vượt hạn mức 1/ngày.
    from app.db.models import ScanRun

    await db.execute(
        update(ScanRun).values(
            scheduled_at=datetime.now(tz=UTC) - timedelta(minutes=20), status="completed"
        )
    )
    await db.commit()
    r = await client.post("/watchlist/scan-now")
    assert r.status_code == 429
    # Operator không bị hạn mức.
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.post(f"/watchlist/scan-now?tenant_id={ids['t1']}")
    assert r.status_code == 202
    # Operator đặt hạn mức qua PATCH /tenants; tenant_admin không đặt được qua /settings.
    r = await client.patch(f"/tenants/{ids['t1']}", json={"limits": {"max_hotels": 50}})
    assert r.status_code == 200 and r.json()["limits"] == {"max_hotels": 50}
    r = await client.patch(f"/tenants/{ids['t1']}", json={"limits": {"bogus": 1}})
    assert r.status_code == 422
    await _login(client, "admin@a.com", "admin-pass-1")
    r = await client.patch("/settings", json={"limits": {"max_hotels": 999}})
    assert r.status_code == 200 and r.json()["limits"] == {"max_hotels": 50}


async def test_metrics_requires_token_and_healthz_checks_db(
    client: AsyncClient, db: AsyncSession, settings: Settings, queue: FakeQueue
) -> None:
    assert (await client.get("/metrics")).status_code == 200  # dev, không token: mở
    r = await client.get("/healthz")
    assert r.status_code == 200 and r.json()["db"] == "ok"
    factory = async_sessionmaker(db.bind, expire_on_commit=False)  # type: ignore[arg-type]
    guarded = Settings(
        _env_file=None,
        database_url="x",
        redis_url="x",
        proxy_url_template="x",
        jwt_secret="test-secret",
        metrics_token="m3trics",
    )
    app = create_app(settings=guarded, session_factory=factory, queue=queue)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            assert (await c.get("/metrics")).status_code == 404
            r = await c.get("/metrics", headers={"Authorization": "Bearer m3trics"})
            assert r.status_code == 200


async def test_pms_upload_limits(client: AsyncClient, db: AsyncSession) -> None:
    ids = await _seed(db)
    await _login(client, "admin@a.com", "admin-pass-1")
    big = b"stay_date,rooms_total\n" + b"2026-10-01,10\n" * 6000
    r = await client.post(
        "/pms/preview", files={"file": ("big.csv", big, "text/csv")}, data={"adapter": "csv"}
    )
    assert r.status_code == 422 and "too many rows" in r.json()["detail"]
    huge = b"x" * (5 * 1024 * 1024 + 1)
    r = await client.post(
        "/pms/preview", files={"file": ("huge.csv", huge, "text/csv")}, data={"adapter": "csv"}
    )
    assert r.status_code == 413
    assert ids["own"]


async def test_user_create_with_unknown_tenant_is_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed(db)
    await _login(client, "op@x.com", "op-pass-123")
    r = await client.post(
        "/users",
        json={"email": "new@x.com", "password": "password-123", "role": "viewer", "tenant_id": 999},
    )
    assert r.status_code == 404
    users = (await db.execute(select(User).where(User.email == "new@x.com"))).scalars().all()
    assert users == []
