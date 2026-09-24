from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.routers import auth, data, health, insights, pms, tenants, watchlist
from app.config import Settings, get_settings
from app.db.engine import make_engine, make_session_factory
from app.logging import configure_logging, get_logger
from app.scheduler.queue import ArqJobQueue

log = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    queue: object | None = None,
) -> FastAPI:
    """Lắp ráp app. Test truyền session_factory và queue giả; production tự tạo trong lifespan."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings or get_settings()
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

    app = FastAPI(
        title="Hotel competitor monitor API",
        version="0.1.0",
        lifespan=lifespan,
    )
    cfg = settings or get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(tenants.router)
    app.include_router(watchlist.router)
    app.include_router(data.router)
    app.include_router(insights.router)
    app.include_router(pms.router)
    app.include_router(health.router)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
