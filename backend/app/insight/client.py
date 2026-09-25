"""Client gọi GPT-6 Luna qua OpenRouter (Chat Completions, chuẩn OpenAI-compatible).

Đồng bộ: `complete()` gọi /chat/completions ngay.
"Batch": OpenRouter KHÔNG có Batch API server-side (cũng không giảm giá batch). Để giữ
nguyên pipeline daily (status batch_pending → cron poll → completed), `submit_batch()` chạy
song song ngay rồi cache kết quả vào một BatchStore (Redis ở production); `poll_batch()` lấy
kết quả ra. Cost tính theo giá list, không có chiết khấu batch.

Giá tham chiếu (research mục 1): $0.10 / 1M input, $0.50 / 1M output.
"""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

from app.insight.schema import INSIGHT_JSON_SCHEMA
from app.logging import get_logger

log = get_logger(__name__)

INPUT_USD_PER_M = Decimal("0.10")
OUTPUT_USD_PER_M = Decimal("0.50")


def estimate_cost(tokens_in: int, tokens_out: int, batch: bool = False) -> Decimal:
    # OpenRouter không có chiết khấu batch; tham số `batch` giữ lại để tương thích chữ ký.
    cost = (
        Decimal(tokens_in) * INPUT_USD_PER_M + Decimal(tokens_out) * OUTPUT_USD_PER_M
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


@dataclass(frozen=True)
class CompletionRequest:
    custom_id: str
    model: str
    system_prompt: str
    user_prompt: str
    input_json: dict[str, Any]
    reasoning_effort: str = "medium"

    @property
    def messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": self.user_prompt
                + json.dumps(self.input_json, ensure_ascii=False, separators=(",", ":")),
            },
        ]

    @property
    def response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "hotel_insight",
                "strict": True,
                "schema": INSIGHT_JSON_SCHEMA,
            },
        }

    def body(self) -> dict[str, Any]:
        """Body Chat Completions chuẩn OpenRouter (reasoning là mở rộng của OpenRouter)."""
        return {
            "model": self.model,
            "messages": self.messages,
            "reasoning": {"effort": self.reasoning_effort},
            "response_format": self.response_format,
        }


@dataclass
class CompletionResult:
    custom_id: str
    output_json: dict[str, Any] | None
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None
    raw_text: str | None = None


@dataclass
class BatchStatus:
    batch_id: str
    status: str  # validating | in_progress | finalizing | completed | failed | expired | cancelled
    results: list[CompletionResult] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return self.status in ("completed", "failed", "expired", "cancelled")


class InsightClient(Protocol):
    async def complete(self, request: CompletionRequest) -> CompletionResult: ...
    async def submit_batch(self, requests: Sequence[CompletionRequest]) -> str: ...
    async def poll_batch(self, batch_id: str) -> BatchStatus: ...


class BatchStore(Protocol):
    """Lưu tạm kết quả batch giữa lúc submit và lúc cron poll (khác lần gọi/tiến trình).

    `get` đọc mà không xóa: poll phải idempotent (nếu commit DB lỗi thì lần poll sau vẫn
    lấy được kết quả), TTL của store lo việc dọn dẹp.
    """

    async def put(self, key: str, value: str) -> None: ...
    async def get(self, key: str) -> str | None: ...


def _parse_output_text(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _result_to_dict(r: CompletionResult) -> dict[str, Any]:
    return {
        "custom_id": r.custom_id,
        "output_json": r.output_json,
        "tokens_in": r.tokens_in,
        "tokens_out": r.tokens_out,
        "error": r.error,
        "raw_text": r.raw_text,
    }


def _result_from_dict(d: dict[str, Any]) -> CompletionResult:
    return CompletionResult(
        custom_id=str(d.get("custom_id", "")),
        output_json=d.get("output_json"),
        tokens_in=int(d.get("tokens_in", 0) or 0),
        tokens_out=int(d.get("tokens_out", 0) or 0),
        error=d.get("error"),
        raw_text=d.get("raw_text"),
    )


class RedisBatchStore:
    """BatchStore trên Redis với TTL (mặc định 48h), key `insight:batch:<id>`."""

    def __init__(self, redis_url: str, ttl_seconds: int = 48 * 3600) -> None:
        from redis.asyncio import from_url

        self._redis = from_url(  # type: ignore[no-untyped-call]
            redis_url, encoding="utf-8", decode_responses=True
        )
        self._ttl = ttl_seconds

    @staticmethod
    def _key(key: str) -> str:
        return f"insight:batch:{key}"

    async def put(self, key: str, value: str) -> None:
        await self._redis.set(self._key(key), value, ex=self._ttl)

    async def get(self, key: str) -> str | None:
        value: str | None = await self._redis.get(self._key(key))
        return value


class OpenRouterInsightClient:
    """Gọi OpenRouter qua SDK openai (base_url trỏ về openrouter.ai)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        *,
        store: BatchStore,
        headers: dict[str, str] | None = None,
        concurrency: int = 8,
        client: Any | None = None,
    ) -> None:
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key, base_url=base_url, default_headers=headers or None
            )
        self._client = client
        self._store = store
        self._sem = asyncio.Semaphore(concurrency)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        # Unpack dict[str, Any] để tránh so khớp overload dict-vs-typed của SDK openai;
        # reasoning là mở rộng của OpenRouter nên đi qua extra_body.
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "response_format": request.response_format,
            "extra_body": {"reasoning": {"effort": request.reasoning_effort}},
        }
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return CompletionResult(request.custom_id, None, error=f"{type(exc).__name__}: {exc}")
        choices = getattr(response, "choices", None) or []
        message = choices[0].message if choices else None
        text = (getattr(message, "content", "") if message else "") or ""
        usage = getattr(response, "usage", None)
        return CompletionResult(
            custom_id=request.custom_id,
            output_json=_parse_output_text(text),
            tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
            tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
            raw_text=text,
            error=None if text else "empty response",
        )

    async def _complete_guarded(self, request: CompletionRequest) -> CompletionResult:
        async with self._sem:
            return await self.complete(request)

    async def submit_batch(self, requests: Sequence[CompletionRequest]) -> str:
        """Chạy song song ngay (OpenRouter không có Batch API), cache kết quả để poll lấy sau."""
        batch_id = f"orbatch_{uuid4().hex}"
        results = await asyncio.gather(*(self._complete_guarded(r) for r in requests))
        await self._store.put(batch_id, json.dumps([_result_to_dict(r) for r in results]))
        log.info("insight_batch_submitted", batch_id=batch_id, requests=len(requests))
        return batch_id

    async def poll_batch(self, batch_id: str) -> BatchStatus:
        raw = await self._store.get(batch_id)
        if raw is None:
            # Chưa submit xong hoặc kết quả đã hết TTL.
            return BatchStatus(batch_id, "in_progress")
        results = [_result_from_dict(d) for d in json.loads(raw)]
        return BatchStatus(batch_id, "completed", results)


class FakeInsightClient:
    """Client giả cho test: trả đầu ra kịch bản sẵn theo custom_id hoặc mặc định."""

    def __init__(self, default_output: dict[str, Any] | None = None) -> None:
        self.default_output = default_output
        self.by_custom_id: dict[str, dict[str, Any]] = {}
        self.requests: list[CompletionRequest] = []
        self.batches: dict[str, list[CompletionRequest]] = {}
        self.batch_status: str = "completed"
        self.fail_with: str | None = None

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        if self.fail_with:
            return CompletionResult(request.custom_id, None, error=self.fail_with)
        output = self.by_custom_id.get(request.custom_id, self.default_output)
        return CompletionResult(request.custom_id, output, tokens_in=20_000, tokens_out=2_000)

    async def submit_batch(self, requests: Sequence[CompletionRequest]) -> str:
        batch_id = f"batch_{len(self.batches) + 1}"
        self.batches[batch_id] = list(requests)
        return batch_id

    async def poll_batch(self, batch_id: str) -> BatchStatus:
        status = BatchStatus(batch_id, self.batch_status)
        if self.batch_status == "completed":
            for r in self.batches[batch_id]:
                out = self.by_custom_id.get(r.custom_id, self.default_output)
                status.results.append(
                    CompletionResult(r.custom_id, out, tokens_in=20_000, tokens_out=2_000)
                )
        return status
