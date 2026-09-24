"""Backup Postgres hằng đêm lên MinIO, giữ N bản gần nhất (spec mục 11)."""

import asyncio
import gzip
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.collector.storage import S3RawStore
from app.config import Settings
from app.logging import get_logger

log = get_logger(__name__)
PREFIX = "postgres/"


def pg_dump_command(database_url: str) -> tuple[list[str], dict[str, str]]:
    """Chuyển DATABASE_URL (SQLAlchemy async) thành lệnh pg_dump + env PGPASSWORD."""
    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    cmd = [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "--format=plain",
        "-h",
        parsed.hostname or "localhost",
        "-p",
        str(parsed.port or 5432),
        "-U",
        parsed.username or "app",
        (parsed.path or "/scrapebooking").lstrip("/"),
    ]
    env = {"PGPASSWORD": parsed.password or ""}
    return cmd, env


async def dump_database(database_url: str) -> bytes:
    import os

    cmd, extra_env = pg_dump_command(database_url)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **extra_env},
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"pg_dump failed ({proc.returncode}): {err.decode(errors='replace')[:500]}"
        )
    return out


def backup_key(now: datetime) -> str:
    return f"{PREFIX}scrapebooking-{now:%Y%m%dT%H%M%SZ}.sql.gz"


def keys_to_delete(keys: list[str], keep: int) -> list[str]:
    """Giữ `keep` bản mới nhất (tên có timestamp nên sort theo tên là theo thời gian)."""
    ordered = sorted(k for k in keys if k.startswith(PREFIX))
    return ordered[:-keep] if len(ordered) > keep else []


async def run_backup(settings: Settings, now: datetime | None = None) -> tuple[str, list[str]]:
    now = now or datetime.now(tz=UTC)
    dump = await dump_database(settings.database_url)
    store = S3RawStore(
        bucket=settings.backup_bucket,
        endpoint_url=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        retention_days=365,
    )
    await store.ensure_bucket()
    key = backup_key(now)
    await store.put_bytes(key, gzip.compress(dump), "application/gzip")
    deleted = keys_to_delete(await store.list_keys(PREFIX), settings.backup_keep)
    for k in deleted:
        await store.delete(k)
    log.info("backup_uploaded", key=key, bytes=len(dump), deleted=deleted)
    return key, deleted
