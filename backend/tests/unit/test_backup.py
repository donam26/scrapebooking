from datetime import UTC, datetime

from app.ops.backup import backup_key, keys_to_delete, pg_dump_command


def test_pg_dump_command_from_sqlalchemy_url() -> None:
    cmd, env = pg_dump_command("postgresql+asyncpg://app:s3cret@db.internal:5433/scrapebooking")
    assert cmd[0] == "pg_dump" and cmd[-1] == "scrapebooking"
    assert cmd[cmd.index("-h") + 1] == "db.internal" and cmd[cmd.index("-p") + 1] == "5433"
    assert cmd[cmd.index("-U") + 1] == "app" and env == {"PGPASSWORD": "s3cret"}


def test_backup_key_and_retention() -> None:
    key = backup_key(datetime(2026, 9, 24, 19, 30, tzinfo=UTC))
    assert key == "postgres/scrapebooking-20260924T193000Z.sql.gz"
    keys = [backup_key(datetime(2026, 9, d, 19, 30, tzinfo=UTC)) for d in range(1, 21)]
    keys.append("other/ignored.txt")
    to_delete = keys_to_delete(keys, keep=14)
    assert len(to_delete) == 6 and to_delete[0].endswith("20260901T193000Z.sql.gz")
    assert keys_to_delete(keys[:5], keep=14) == []
