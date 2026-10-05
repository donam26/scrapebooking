"""Client gọi GPT-6 Luna qua OpenRouter (Chat Completions, chuẩn OpenAI-compatible).

Chỉ có một đường gọi đồng bộ `complete()`: OpenRouter không có Batch API server-side và
không giảm giá batch, nên bản tin hằng ngày và theo yêu cầu đều gọi thẳng /chat/completions.

Giá tham chiếu (research mục 1): $0.10 / 1M input, $0.50 / 1M output.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.insight.schema import INSIGHT_JSON_SCHEMA
from app.logging import get_logger

log = get_logger(__name__)

INPUT_USD_PER_M = Decimal("0.10")
OUTPUT_USD_PER_M = Decimal("0.50")
# Ước lượng thô khi nhà cung cấp không trả usage: ~4 ký tự / token.
CHARS_PER_TOKEN = 4


def estimate_cost(tokens_in: int, tokens_out: int) -> Decimal:
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
    def input_text(self) -> str:
        return json.dumps(self.input_json, ensure_ascii=False, separators=(",", ":"))

    @property
    def messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_prompt + self.input_text},
        ]

    @property
    def estimated_input_tokens(self) -> int:
        """Ước lượng kích thước đầu vào (ký tự / 4) để ghi log và thay usage khi thiếu."""
        return sum(len(m["content"]) for m in self.messages) // CHARS_PER_TOKEN

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


class InsightClient(Protocol):
    async def complete(self, request: CompletionRequest) -> CompletionResult: ...


def _parse_output_text(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class OpenRouterInsightClient:
    """Gọi OpenRouter qua SDK openai (base_url trỏ về openrouter.ai).

    Giới hạn mỗi lần gọi: `max_tokens` đầu ra, timeout HTTP và tối đa 1 lần thử lại của SDK
    (mặc định SDK là 600 s × 2 lần thử lại, đủ treo worker gần 1 giờ)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        *,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = 1,
        max_output_tokens: int = 4096,
        client: Any | None = None,
    ) -> None:
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                default_headers=headers or None,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        estimated_in = request.estimated_input_tokens
        log.info(
            "insight_request",
            custom_id=request.custom_id,
            model=request.model,
            estimated_tokens_in=estimated_in,
            max_tokens=self._max_output_tokens,
        )
        # Unpack dict[str, Any] để tránh so khớp overload dict-vs-typed của SDK openai;
        # reasoning là mở rộng của OpenRouter nên đi qua extra_body.
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "response_format": request.response_format,
            "max_tokens": self._max_output_tokens,
            "extra_body": {"reasoning": {"effort": request.reasoning_effort}},
        }
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return CompletionResult(
                request.custom_id,
                None,
                tokens_in=estimated_in,
                error=f"{type(exc).__name__}: {exc}",
            )
        choices = getattr(response, "choices", None) or []
        message = choices[0].message if choices else None
        text = (getattr(message, "content", "") if message else "") or ""
        usage = getattr(response, "usage", None)
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        if not tokens_in:
            log.warning("insight_usage_missing", custom_id=request.custom_id)
            tokens_in = estimated_in
        return CompletionResult(
            custom_id=request.custom_id,
            output_json=_parse_output_text(text),
            tokens_in=tokens_in,
            tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
            raw_text=text,
            error=None if text else "empty response",
        )


class FakeInsightClient:
    """Client giả cho test: trả đầu ra kịch bản sẵn theo custom_id hoặc mặc định."""

    def __init__(self, default_output: dict[str, Any] | None = None) -> None:
        self.default_output = default_output
        self.by_custom_id: dict[str, dict[str, Any]] = {}
        self.requests: list[CompletionRequest] = []
        self.fail_with: str | None = None

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        if self.fail_with:
            return CompletionResult(request.custom_id, None, error=self.fail_with)
        output = self.by_custom_id.get(request.custom_id, self.default_output)
        return CompletionResult(request.custom_id, output, tokens_in=20_000, tokens_out=2_000)
