"""Backup Postgres hằng đêm lên bucket S3-compatible (MinIO), giữ N bản gần nhất (spec mục 11).

`pg_dump -Fc | gzip` chạy thành hai tiến trình nối ống, ghi vào một file tạm (không giữ dump
trong RAM, không nén trên event loop), rồi upload multipart (`upload_fileobj`) trong thread.
Khôi phục: `gunzip -c <file> | pg_restore --no-owner -d <db>` (xem infra/scripts/restore-drill.sh).
"""

import asyncio
import os
import tempfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import Settings
from app.logging import get_logger
from app.ops.metrics import BACKUPS_TOTAL

log = get_logger(__name__)
PREFIX = "postgres/"
CONTENT_TYPE = "application/gzip"
# pg_dump -Fc tự nén từng object: tắt (-Z0) để gzip phía sau nén một lần, file .gz tải/giải nén
# bằng công cụ chuẩn.
GZIP_COMMAND = ["gzip", "-c", "-6"]

Pipeline = list[list[str]]
PipelineRunner = Callable[[Pipeline, dict[str, str], Path], Awaitable[None]]


def pg_dump_command(database_url: str) -> tuple[list[str], dict[str, str]]:
    """Chuyển DATABASE_URL (SQLAlchemy async) thành lệnh pg_dump (định dạng custom) + env
    PGPASSWORD."""
    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    cmd = [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "--format=custom",
        "--compress=0",
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


def backup_pipeline(database_url: str) -> tuple[Pipeline, dict[str, str]]:
    """`pg_dump … | gzip -c`: các stage nối ống, env bổ sung cho mọi stage."""
    cmd, env = pg_dump_command(database_url)
    return [cmd, list(GZIP_COMMAND)], env


async def run_pipeline(stages: Pipeline, env: dict[str, str], dest: Path) -> None:
    """Chạy `stages[0] | stages[1] | … > dest` như shell, không qua shell. Stage nào thoát khác 0
    thì raise RuntimeError kèm stderr của stage đó."""
    if not stages:
        raise ValueError("pipeline rỗng")
    full_env = {**os.environ, **env}
    pipes = [os.pipe() for _ in stages[:-1]]  # (đọc, ghi) giữa stage i và i+1
    procs: list[asyncio.subprocess.Process] = []
    try:
        with dest.open("wb") as out:
            for i, cmd in enumerate(stages):
                stdin = pipes[i - 1][0] if i > 0 else None
                stdout = pipes[i][1] if i < len(stages) - 1 else out
                procs.append(
                    await asyncio.create_subprocess_exec(
                        *cmd,
                        stdin=stdin,
                        stdout=stdout,
                        stderr=asyncio.subprocess.PIPE,
                        env=full_env,
                    )
                )
    except BaseException:
        for p in procs:
            if p.returncode is None:
                p.kill()
        raise
    finally:
        # Tiến trình con đã giữ bản sao fd: đóng bản của tiến trình cha để EOF lan đúng chiều.
        for r, w in pipes:
            os.close(r)
            os.close(w)
        if procs and len(procs) < len(stages):
            await asyncio.gather(*(p.wait() for p in procs), return_exceptions=True)

    # Đọc stderr trước khi chờ: ống stderr đầy sẽ làm tiến trình con treo.
    errors = await asyncio.gather(*(_read_stderr(p) for p in procs))
    codes = await asyncio.gather(*(p.wait() for p in procs))
    failed = [
        f"{cmd[0]} ({code}): {err.decode(errors='replace').strip()[:500]}"
        for cmd, code, err in zip(stages, codes, errors, strict=True)
        if code != 0
    ]
    if failed:
        raise RuntimeError("backup pipeline failed: " + "; ".join(failed))


async def _read_stderr(proc: asyncio.subprocess.Process) -> bytes:
    return await proc.stderr.read() if proc.stderr is not None else b""


async def dump_database(
    database_url: str, dest: Path, runner: PipelineRunner = run_pipeline
) -> int:
    """pg_dump -Fc | gzip → `dest`. Trả số byte đã ghi."""
    stages, env = backup_pipeline(database_url)
    await runner(stages, env, dest)
    return (await asyncio.to_thread(dest.stat)).st_size


def backup_key(now: datetime) -> str:
    return f"{PREFIX}scrapebooking-{now:%Y%m%dT%H%M%SZ}.dump.gz"


def keys_to_delete(keys: list[str], keep: int) -> list[str]:
    """Giữ `keep` bản mới nhất (tên có timestamp nên sort theo tên là theo thời gian; bản plain
    `.sql.gz` cũ và bản `.dump.gz` xếp chung một dãy)."""
    ordered = sorted(k for k in keys if k.startswith(PREFIX))
    return ordered[:-keep] if len(ordered) > keep else []


class BackupStore(Protocol):
    async def ensure_bucket(self) -> None: ...
    async def upload_file(self, key: str, path: Path, content_type: str) -> None: ...
    async def list_keys(self, prefix: str) -> list[str]: ...
    async def delete(self, key: str) -> None: ...


class S3BackupStore:
    """Bucket S3-compatible cho backup: MinIO cùng máy (mặc định) hoặc đích offsite (B2/Wasabi/S3).
    Không đặt lifecycle rule: số bản giữ lại do `keys_to_delete` quyết định."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        self._bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=BotoConfig(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    def _ensure_bucket_sync(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    def _upload_sync(self, key: str, path: Path, content_type: str) -> None:
        # upload_fileobj tự chia multipart và stream từ file: không đọc cả dump vào RAM.
        with path.open("rb") as f:
            self._client.upload_fileobj(
                f, self._bucket, key, ExtraArgs={"ContentType": content_type}
            )

    async def upload_file(self, key: str, path: Path, content_type: str) -> None:
        await asyncio.to_thread(self._upload_sync, key, path, content_type)

    def _list_keys_sync(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return sorted(keys)

    async def list_keys(self, prefix: str = "") -> list[str]:
        return await asyncio.to_thread(self._list_keys_sync, prefix)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)


def backup_store(settings: Settings) -> S3BackupStore:
    """Đích backup. Khi Settings có `backup_endpoint`/`backup_access_key`/`backup_secret_key`
    (đích offsite, khác MinIO cùng máy) thì dùng; để trống/chưa có thì dùng MinIO của hệ thống."""
    endpoint = getattr(settings, "backup_endpoint", "") or settings.minio_endpoint
    access_key = getattr(settings, "backup_access_key", "") or settings.minio_access_key
    secret_key = getattr(settings, "backup_secret_key", "") or settings.minio_secret_key
    return S3BackupStore(settings.backup_bucket, endpoint, access_key, secret_key)


async def run_backup(
    settings: Settings,
    now: datetime | None = None,
    *,
    store: BackupStore | None = None,
    runner: PipelineRunner = run_pipeline,
) -> tuple[str, list[str]]:
    """Dump → file tạm (cần dung lượng đĩa ≈ kích thước bản nén ở TMPDIR) → upload → xoá bản cũ."""
    now = now or datetime.now(tz=UTC)
    store = store or backup_store(settings)
    key = backup_key(now)
    fd, tmp_name = tempfile.mkstemp(prefix="sb-backup-", suffix=".dump.gz")
    os.close(fd)
    path = Path(tmp_name)
    try:
        size = await dump_database(settings.database_url, path, runner)
        await store.ensure_bucket()
        await store.upload_file(key, path, CONTENT_TYPE)
        deleted = keys_to_delete(await store.list_keys(PREFIX), settings.backup_keep)
        for k in deleted:
            await store.delete(k)
    except Exception:
        BACKUPS_TOTAL.labels("error").inc()
        raise
    finally:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    BACKUPS_TOTAL.labels("ok").inc()
    log.info("backup_uploaded", key=key, bytes=size, deleted=deleted)
    return key, deleted
