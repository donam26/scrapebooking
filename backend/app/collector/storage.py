import asyncio
import gzip
from datetime import date, datetime
from typing import Any, Protocol

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


def raw_key(scan_run_id: int, hotel_id: int, stay_date: date, fetched_at: datetime) -> str:
    return f"{fetched_at:%Y/%m/%d}/run{scan_run_id}/hotel{hotel_id}/{stay_date.isoformat()}.html.gz"


class RawStore(Protocol):
    async def put_html(self, key: str, html: str) -> None: ...
    async def get_html(self, key: str) -> str | None: ...


class MemoryRawStore:
    def __init__(self) -> None:
        self.items: dict[str, str] = {}

    async def put_html(self, key: str, html: str) -> None:
        self.items[key] = html

    async def get_html(self, key: str) -> str | None:
        return self.items.get(key)


class S3RawStore:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        retention_days: int = 30,
    ) -> None:
        self._bucket = bucket
        self._retention_days = retention_days
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
        # HTML thô chỉ giữ `retention_days` ngày (spec mục 5.4), MinIO tự xoá.
        self._client.put_bucket_lifecycle_configuration(
            Bucket=self._bucket,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": "expire-raw-html",
                        "Status": "Enabled",
                        "Filter": {"Prefix": ""},
                        "Expiration": {"Days": self._retention_days},
                    }
                ]
            },
        )

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def put_html(self, key: str, html: str) -> None:
        body = gzip.compress(html.encode("utf-8"))
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="text/html; charset=utf-8",
            ContentEncoding="gzip",
        )

    def _get_sync(self, key: str) -> str | None:
        try:
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return gzip.decompress(obj["Body"].read()).decode("utf-8")

    async def get_html(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_sync, key)

    # ---- dùng cho backup (giai đoạn 5) ----

    async def put_bytes(self, key: str, body: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

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
