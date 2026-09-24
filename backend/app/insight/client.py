"""Client gọi GPT-6 Luna qua OpenAI Responses API (đồng bộ) và Batch API (hằng ngày).

Giá tham chiếu (research mục 1): $0.10 / 1M input, $0.50 / 1M output, batch giảm 50%.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from app.insight.schema import INSIGHT_JSON_SCHEMA
from app.logging import get_logger

log = get_logger(__name__)

INPUT_USD_PER_M = Decimal("0.10")
OUTPUT_USD_PER_M = Decimal("0.50")
BATCH_DISCOUNT = Decimal("0.5")


def estimate_cost(tokens_in: int, tokens_out: int, batch: bool = False) -> Decimal:
    cost = (
        Decimal(tokens_in) * INPUT_USD_PER_M + Decimal(tokens_out) * OUTPUT_USD_PER_M
    ) / Decimal(1_000_000)
    if batch:
        cost *= BATCH_DISCOUNT
    return cost.quantize(Decimal("0.000001"))


@dataclass(frozen=True)
class CompletionRequest:
    custom_id: str
    model: str
    system_prompt: str
    user_prompt: str
    input_json: dict[str, Any]
    reasoning_effort: str = "medium"

    def body(self) -> dict[str, Any]:
        """Body Responses API, dùng cho cả gọi đồng bộ lẫn dòng JSONL của Batch."""
        return {
            "model": self.model,
            "reasoning": {"effort": self.reasoning_effort},
            "input": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": self.user_prompt
                    + json.dumps(self.input_json, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "hotel_insight",
                    "schema": INSIGHT_JSON_SCHEMA,
                    "strict": True,
                }
            },
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


def _parse_output_text(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class OpenAIInsightClient:
    def __init__(self, api_key: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            response = await self._client.responses.create(**request.body())
        except Exception as exc:  # noqa: BLE001
            return CompletionResult(request.custom_id, None, error=f"{type(exc).__name__}: {exc}")
        text = getattr(response, "output_text", "") or ""
        usage = getattr(response, "usage", None)
        return CompletionResult(
            custom_id=request.custom_id,
            output_json=_parse_output_text(text),
            tokens_in=int(getattr(usage, "input_tokens", 0) or 0),
            tokens_out=int(getattr(usage, "output_tokens", 0) or 0),
            raw_text=text,
            error=None if text else "empty response",
        )

    async def submit_batch(self, requests: Sequence[CompletionRequest]) -> str:
        lines = [
            json.dumps(
                {
                    "custom_id": r.custom_id,
                    "method": "POST",
                    "url": "/v1/responses",
                    "body": r.body(),
                },
                ensure_ascii=False,
            )
            for r in requests
        ]
        content = ("\n".join(lines) + "\n").encode("utf-8")
        uploaded = await self._client.files.create(
            file=("insight_batch.jsonl", content), purpose="batch"
        )
        batch = await self._client.batches.create(
            input_file_id=uploaded.id, endpoint="/v1/responses", completion_window="24h"
        )
        log.info("insight_batch_submitted", batch_id=batch.id, requests=len(requests))
        return str(batch.id)

    async def poll_batch(self, batch_id: str) -> BatchStatus:
        batch = await self._client.batches.retrieve(batch_id)
        status = BatchStatus(batch_id, str(batch.status))
        if batch.status != "completed":
            return status
        for file_id in (batch.output_file_id, batch.error_file_id):
            if not file_id:
                continue
            content = await self._client.files.content(file_id)
            text = content.text if hasattr(content, "text") else content.read().decode("utf-8")
            for line in text.splitlines():
                if not line.strip():
                    continue
                status.results.append(parse_batch_line(json.loads(line)))
        return status


def parse_batch_line(row: dict[str, Any]) -> CompletionResult:
    """Một dòng output JSONL của Batch API cho endpoint /v1/responses."""
    custom_id = str(row.get("custom_id", ""))
    err = row.get("error")
    if err:
        return CompletionResult(custom_id, None, error=str(err.get("message") or err))
    response = row.get("response") or {}
    body = response.get("body") or {}
    if response.get("status_code", 200) != 200:
        return CompletionResult(
            custom_id, None, error=f"http {response.get('status_code')}: {body}"
        )
    text = body.get("output_text")
    if text is None:
        # Responses API: output[].content[].text
        parts = []
        for item in body.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") in ("output_text", "text") and c.get("text"):
                    parts.append(c["text"])
        text = "".join(parts)
    usage = body.get("usage") or {}
    return CompletionResult(
        custom_id=custom_id,
        output_json=_parse_output_text(text or ""),
        tokens_in=int(usage.get("input_tokens", 0) or 0),
        tokens_out=int(usage.get("output_tokens", 0) or 0),
        raw_text=text,
        error=None if text else "empty response",
    )


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
