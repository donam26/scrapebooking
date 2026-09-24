from datetime import UTC, date, datetime

import pytest
from moto import mock_aws

from app.collector.storage import MemoryRawStore, S3RawStore, raw_key


def test_raw_key_layout() -> None:
    key = raw_key(
        scan_run_id=7,
        hotel_id=42,
        stay_date=date(2026, 10, 5),
        fetched_at=datetime(2026, 9, 24, 6, 5, tzinfo=UTC),
    )
    assert key == "2026/09/24/run7/hotel42/2026-10-05.html.gz"


async def test_memory_store_roundtrip() -> None:
    store = MemoryRawStore()
    await store.put_html("a/b.html.gz", "<html>x</html>")
    assert await store.get_html("a/b.html.gz") == "<html>x</html>"
    assert await store.get_html("missing") is None


@pytest.fixture
def aws_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


async def test_s3_store_roundtrip_with_moto(aws_env: None) -> None:
    with mock_aws():
        store = S3RawStore(
            bucket="raw-html", endpoint_url=None, access_key="testing", secret_key="testing"
        )
        await store.ensure_bucket()
        await store.put_html("2026/09/24/run1/hotel1/2026-10-01.html.gz", "<html>hi</html>")
        assert (
            await store.get_html("2026/09/24/run1/hotel1/2026-10-01.html.gz") == "<html>hi</html>"
        )
        assert await store.get_html("nope") is None
        rules = store._client.get_bucket_lifecycle_configuration(Bucket="raw-html")["Rules"]
        assert rules[0]["Expiration"]["Days"] == 30


async def test_s3_store_bytes_list_delete_with_moto(aws_env: None) -> None:
    with mock_aws():
        store = S3RawStore(
            bucket="pg-backups", endpoint_url=None, access_key="testing", secret_key="testing"
        )
        await store.ensure_bucket()
        await store.put_bytes("backups/a.sql.gz", b"x", "application/gzip")
        await store.put_bytes("backups/b.sql.gz", b"y", "application/gzip")
        assert await store.list_keys("backups/") == ["backups/a.sql.gz", "backups/b.sql.gz"]
        await store.delete("backups/a.sql.gz")
        assert await store.list_keys("backups/") == ["backups/b.sql.gz"]
