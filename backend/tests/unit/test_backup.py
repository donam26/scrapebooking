import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.ops.backup import (
    CONTENT_TYPE,
    GZIP_COMMAND,
    PREFIX,
    backup_key,
    backup_pipeline,
    keys_to_delete,
    pg_dump_command,
    run_backup,
    run_pipeline,
)


def test_pg_dump_command_from_sqlalchemy_url() -> None:
    cmd, env = pg_dump_command("postgresql+asyncpg://app:s3cret@db.internal:5433/scrapebooking")
    assert cmd[0] == "pg_dump" and cmd[-1] == "scrapebooking"
    assert "--format=custom" in cmd and "--compress=0" in cmd  # gzip phía sau nén một lần
    assert cmd[cmd.index("-h") + 1] == "db.internal" and cmd[cmd.index("-p") + 1] == "5433"
    assert cmd[cmd.index("-U") + 1] == "app" and env == {"PGPASSWORD": "s3cret"}


def test_backup_pipeline_is_pg_dump_piped_into_gzip() -> None:
    stages, env = backup_pipeline("postgresql+asyncpg://app:pw@h:5432/db")
    assert [s[0] for s in stages] == ["pg_dump", "gzip"] and stages[1] == GZIP_COMMAND
    assert env == {"PGPASSWORD": "pw"}


def test_backup_key_and_retention() -> None:
    key = backup_key(datetime(2026, 9, 24, 19, 30, tzinfo=UTC))
    assert key == "postgres/scrapebooking-20260924T193000Z.dump.gz"
    keys = [backup_key(datetime(2026, 9, d, 19, 30, tzinfo=UTC)) for d in range(1, 21)]
    keys.append("other/ignored.txt")
    keys.append("postgres/scrapebooking-20260815T193000Z.sql.gz")  # bản plain cũ cùng dãy
    to_delete = keys_to_delete(keys, keep=14)
    assert len(to_delete) == 7 and to_delete[0].endswith("20260815T193000Z.sql.gz")
    assert keys_to_delete(keys[:5], keep=14) == []


async def test_run_pipeline_streams_through_stages_into_file(tmp_path: Path) -> None:
    dest = tmp_path / "out.gz"
    await run_pipeline([["sh", "-c", "printf hello"], ["gzip", "-c"]], {}, dest)
    assert gzip.decompress(dest.read_bytes()) == b"hello"


async def test_run_pipeline_reports_failed_stage_with_stderr(tmp_path: Path) -> None:
    stages = [["sh", "-c", "echo boom >&2; exit 3"], ["gzip", "-c"]]
    with pytest.raises(RuntimeError, match=r"sh \(3\): boom"):
        await run_pipeline(stages, {}, tmp_path / "out.gz")


class FakeStore:
    def __init__(self, existing: list[str]) -> None:
        self.keys = list(existing)
        self.uploaded: list[tuple[str, bytes, str]] = []
        self.deleted: list[str] = []
        self.bucket_ensured = False

    async def ensure_bucket(self) -> None:
        self.bucket_ensured = True

    async def upload_file(self, key: str, path: Path, content_type: str) -> None:
        self.uploaded.append((key, path.read_bytes(), content_type))  # noqa: ASYNC240
        self.keys.append(key)

    async def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.keys if k.startswith(prefix))

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.keys.remove(key)


def _settings(keep: int) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://app:pw@db:5432/scrapebooking",
        redis_url="x",
        proxy_url_template="x",
        backup_keep=keep,
    )


async def test_run_backup_dumps_to_temp_file_uploads_and_prunes() -> None:
    seen: dict[str, object] = {}

    async def fake_runner(stages: list[list[str]], env: dict[str, str], dest: Path) -> None:
        seen["stages"] = [s[0] for s in stages]
        seen["env"] = env
        seen["dest"] = dest
        dest.write_bytes(b"dump-bytes")  # noqa: ASYNC240

    old = [backup_key(datetime(2026, 9, d, 19, 30, tzinfo=UTC)) for d in (1, 2, 3)]
    store = FakeStore(old)
    key, deleted = await run_backup(
        _settings(keep=2),
        datetime(2026, 9, 4, 19, 30, tzinfo=UTC),
        store=store,
        runner=fake_runner,
    )
    assert key == "postgres/scrapebooking-20260904T193000Z.dump.gz"
    assert seen["stages"] == ["pg_dump", "gzip"] and seen["env"] == {"PGPASSWORD": "pw"}
    assert store.bucket_ensured and store.uploaded == [(key, b"dump-bytes", CONTENT_TYPE)]
    assert deleted == old[:2] and store.deleted == old[:2]
    assert sorted(store.keys) == [old[2], key]
    dest = seen["dest"]
    assert isinstance(dest, Path) and not dest.exists()  # file tạm đã được xoá


async def test_run_backup_failure_removes_temp_file_and_uploads_nothing() -> None:
    created: list[Path] = []

    async def failing_runner(stages: list[list[str]], env: dict[str, str], dest: Path) -> None:
        created.append(dest)
        dest.write_bytes(b"partial")  # noqa: ASYNC240
        raise RuntimeError("pg_dump failed (1): connection refused")

    store = FakeStore([f"{PREFIX}scrapebooking-20260901T193000Z.dump.gz"])
    with pytest.raises(RuntimeError, match="pg_dump failed"):
        await run_backup(_settings(keep=2), store=store, runner=failing_runner)
    assert store.uploaded == [] and store.deleted == []
    assert created and not created[0].exists()
