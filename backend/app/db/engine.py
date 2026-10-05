import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Mặc định cho api/scheduler (truy vấn ngắn). Tiến trình làm việc dài hơi (jobs: analytics một run,
# insight gọi model tới 120 s trong một session; worker) đặt giá trị lớn hơn qua env trong compose
# (DB_STATEMENT_TIMEOUT_MS, DB_IDLE_IN_TRANSACTION_TIMEOUT_MS) mà không phải sửa chỗ gọi.
# 0 = tắt (theo Postgres).
DEFAULT_STATEMENT_TIMEOUT_MS = 30_000
DEFAULT_IDLE_IN_TRANSACTION_TIMEOUT_MS = 60_000
STATEMENT_TIMEOUT_ENV = "DB_STATEMENT_TIMEOUT_MS"
IDLE_IN_TRANSACTION_TIMEOUT_ENV = "DB_IDLE_IN_TRANSACTION_TIMEOUT_MS"


def _timeout_ms(explicit: int | None, env_name: str, default: int) -> int:
    if explicit is not None:
        return explicit
    raw = os.environ.get(env_name, "").strip()
    return int(raw) if raw.isdigit() else default


def server_settings(
    statement_timeout_ms: int | None = None, idle_in_transaction_timeout_ms: int | None = None
) -> dict[str, str]:
    """Tham số phiên Postgres gửi lúc kết nối (asyncpg `server_settings`, giá trị dạng chuỗi)."""
    return {
        "statement_timeout": str(
            _timeout_ms(statement_timeout_ms, STATEMENT_TIMEOUT_ENV, DEFAULT_STATEMENT_TIMEOUT_MS)
        ),
        "idle_in_transaction_session_timeout": str(
            _timeout_ms(
                idle_in_transaction_timeout_ms,
                IDLE_IN_TRANSACTION_TIMEOUT_ENV,
                DEFAULT_IDLE_IN_TRANSACTION_TIMEOUT_MS,
            )
        ),
    }


def make_engine(
    database_url: str,
    *,
    statement_timeout_ms: int | None = None,
    idle_in_transaction_timeout_ms: int | None = None,
) -> AsyncEngine:
    """Engine asyncpg với `statement_timeout` và `idle_in_transaction_session_timeout` đặt ở mức kết
    nối, để một truy vấn treo hay transaction bỏ quên (chờ SMTP, chờ model…) không giữ kết nối mãi.
    Tham số None → env `DB_*_TIMEOUT_MS` → mặc định 30 s / 60 s."""
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={
            "server_settings": server_settings(statement_timeout_ms, idle_in_transaction_timeout_ms)
        },
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
