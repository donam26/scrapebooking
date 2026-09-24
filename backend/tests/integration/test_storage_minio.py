import socket
import uuid
from urllib.parse import urlparse

import pytest

from app.collector.storage import S3RawStore
from app.config import Settings


def _minio_reachable(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    try:
        with socket.create_connection(
            (parsed.hostname or "localhost", parsed.port or 9000), timeout=1
        ):
            return True
    except OSError:
        return False


async def test_minio_roundtrip() -> None:
    s = Settings(_env_file=None, database_url="x", redis_url="x", proxy_url_template="x")
    if not _minio_reachable(s.minio_endpoint):
        pytest.skip(f"MinIO not reachable at {s.minio_endpoint}")
    store = S3RawStore(
        bucket=s.minio_bucket,
        endpoint_url=s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
    )
    await store.ensure_bucket()
    key = f"test/{uuid.uuid4()}.html.gz"
    await store.put_html(key, "<html>minio</html>")
    assert await store.get_html(key) == "<html>minio</html>"
