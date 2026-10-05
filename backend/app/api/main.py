from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.routers import (
    auth,
    data,
    export,
    health,
    insights,
    market,
    market_city,
    notifications,
    pms,
    tenants,
    watchlist,
)
from app.config import Settings, get_settings
from app.db.engine import make_engine, make_session_factory
from app.logging import configure_logging, get_logger
from app.scheduler.queue import ArqJobQueue

log = get_logger(__name__)

# Phương thức có thể đổi trạng thái: trình duyệt luôn gửi Origin cho request cross-site, nên kiểm
# Origin/Referer là đủ chống CSRF cho cookie SameSite=Lax (chặn cả subdomain cùng site).
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_DEFAULT_JWT_SECRET = "change-me"


class InsecureConfiguration(RuntimeError):
    """Cấu hình không được phép chạy ở production (jwt_secret mặc định, cookie không secure…)."""


def check_production_settings(cfg: Settings) -> None:
    if cfg.app_env != "prod":
        return
    problems: list[str] = []
    if cfg.jwt_secret == _DEFAULT_JWT_SECRET or len(cfg.jwt_secret) < 32:
        problems.append("JWT_SECRET must be a random string of at least 32 characters")
    if not cfg.cookie_secure:
        problems.append("COOKIE_SECURE must be true (dashboard served over https)")
    if "*" in cfg.cors_origin_list:
        problems.append("CORS_ORIGINS must list explicit origins, not *")
    if cfg.app_base_url.startswith("http://") and "localhost" not in cfg.app_base_url:
        problems.append("APP_BASE_URL must be https in production")
    if problems:
        raise InsecureConfiguration("; ".join(problems))


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme and parts.netloc else ""


def trusted_origins(cfg: Settings) -> set[str]:
    origins = {_origin(cfg.app_base_url), *(_origin(o) for o in cfg.cors_origin_list)}
    return {o for o in origins if o}


def csrf_rejection(request: Request, trusted: set[str]) -> str | None:
    """Lý do từ chối request đổi trạng thái đến từ site khác; None nếu hợp lệ."""
    if request.method not in _UNSAFE_METHODS:
        return None
    if request.cookies.get("sb_session") is None:
        return None  # không dùng cookie (Bearer, CLI): CSRF không áp dụng
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return "cross-site request"
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        origin = _origin(referer) if referer else None
    if origin is None:
        return None  # client không phải trình duyệt
    if origin.lower() == "null" or origin.lower() not in trusted:
        return f"origin {origin} not allowed"
    return None


def create_app(
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    queue: object | None = None,
) -> FastAPI:
    """Lắp ráp app. Test truyền session_factory và queue giả; production tự tạo trong lifespan."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings or get_settings()
        check_production_settings(cfg)
        configure_logging(cfg.log_level)
        app.state.settings = cfg
        engine = None
        if session_factory is None:
            engine = make_engine(cfg.database_url)
            app.state.session_factory = make_session_factory(engine)
        else:
            app.state.session_factory = session_factory
        if queue is not None:
            app.state.queue = queue
        else:
            try:
                app.state.queue = await ArqJobQueue.connect(cfg.redis_url)
            except Exception as exc:  # noqa: BLE001
                log.warning("api_queue_unavailable", error=str(exc))
                app.state.queue = None
        log.info("api_started")
        try:
            yield
        finally:
            if queue is None and app.state.queue is not None:
                await app.state.queue.close()
            if engine is not None:
                await engine.dispose()

    cfg = settings or get_settings()
    production = cfg.app_env == "prod"
    app = FastAPI(
        title="Hotel competitor monitor API",
        version="0.1.0",
        lifespan=lifespan,
        # Production: không công khai tài liệu API (OpenAPI vẫn export được bằng script).
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    trusted = trusted_origins(cfg)

    @app.middleware("http")
    async def csrf_guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        reason = csrf_rejection(request, trusted)
        if reason is not None:
            log.warning("csrf_rejected", path=request.url.path, reason=reason)
            return JSONResponse({"detail": f"csrf check failed: {reason}"}, status_code=403)
        return await call_next(request)

    app.include_router(auth.router)
    app.include_router(tenants.router)
    app.include_router(watchlist.router)
    app.include_router(watchlist.channels_router)
    app.include_router(data.router)
    app.include_router(insights.router)
    app.include_router(pms.router)
    app.include_router(notifications.router)
    app.include_router(export.router)
    app.include_router(market.router)
    app.include_router(market_city.router)
    app.include_router(health.router)

    @app.get("/healthz", tags=["health"])
    async def healthz(request: Request) -> dict[str, str]:
        """Sẵn sàng phục vụ: DB trả lời và (nếu có) Redis trả lời. 503 kèm thành phần lỗi."""
        checks: dict[str, str] = {}
        try:
            async with request.app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["db"] = f"error: {type(exc).__name__}"
        queue = getattr(request.app.state, "queue", None)
        redis = getattr(queue, "redis", None)
        if redis is not None:
            try:
                await redis.ping()
                checks["redis"] = "ok"
            except Exception as exc:  # noqa: BLE001
                checks["redis"] = f"error: {type(exc).__name__}"
        if any(v != "ok" for v in checks.values()):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=checks)
        return {"status": "ok", **checks}

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        """Prometheus. Có METRICS_TOKEN thì cần `Authorization: Bearer`; production không có token
        thì không mở."""
        token = cfg.metrics_token
        if token:
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {token}":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        elif production:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
