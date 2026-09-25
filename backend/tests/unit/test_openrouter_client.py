"""Unit test cho OpenRouterInsightClient: shape request Chat Completions, parse kết quả,
và vòng batch (submit chạy ngay -> store -> poll lấy ra)."""

import json
from types import SimpleNamespace
from typing import Any

from app.insight.client import (
    CompletionRequest,
    OpenRouterInsightClient,
    _parse_output_text,
)
from app.insight.schema import INSIGHT_JSON_SCHEMA

_OUTPUT = {
    "summary": "ok",
    "highlights": [],
    "demand_signals": [],
    "pricing_opportunities": [],
    "risks": [],
    "data_quality_note": "",
}


class _DictStore:
    def __init__(self) -> None:
        self.d: dict[str, str] = {}

    async def put(self, key: str, value: str) -> None:
        self.d[key] = value

    async def get(self, key: str) -> str | None:
        return self.d.get(key)


class _FakeCompletions:
    def __init__(self, content: str, calls: list[dict[str, Any]]) -> None:
        self._content = content
        self._calls = calls

    async def create(self, **kwargs: Any) -> Any:
        self._calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(prompt_tokens=123, completion_tokens=45),
        )


class _FakeAsyncOpenAI:
    def __init__(self, content: str) -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=_FakeCompletions(content, self.calls))


def _request(custom_id: str = "insight-1") -> CompletionRequest:
    return CompletionRequest(custom_id, "openai/gpt-6-luna", "SYS", "USER:", {"a": 1}, "high")


async def test_complete_shapes_chat_completions_and_parses() -> None:
    fake = _FakeAsyncOpenAI(json.dumps(_OUTPUT))
    client = OpenRouterInsightClient(store=_DictStore(), client=fake)

    result = await client.complete(_request())

    assert result.output_json == _OUTPUT
    assert result.tokens_in == 123 and result.tokens_out == 45 and result.error is None
    call = fake.calls[0]
    assert call["model"] == "openai/gpt-6-luna"
    assert call["messages"][0] == {"role": "system", "content": "SYS"}
    assert call["messages"][1]["content"].endswith('{"a":1}')
    assert call["response_format"]["json_schema"]["schema"] == INSIGHT_JSON_SCHEMA
    assert call["extra_body"] == {"reasoning": {"effort": "high"}}


async def test_complete_empty_content_is_error() -> None:
    client = OpenRouterInsightClient(store=_DictStore(), client=_FakeAsyncOpenAI(""))
    result = await client.complete(_request())
    assert result.output_json is None and result.error == "empty response"


async def test_batch_submit_runs_now_and_poll_returns_results() -> None:
    store = _DictStore()
    fake = _FakeAsyncOpenAI(json.dumps(_OUTPUT))
    client = OpenRouterInsightClient(store=store, client=fake)

    batch_id = await client.submit_batch([_request("insight-1"), _request("insight-2")])
    assert batch_id.startswith("orbatch_")
    assert len(fake.calls) == 2  # đã gọi ngay lúc submit
    assert batch_id in store.d  # kết quả đã được cache

    status = await client.poll_batch(batch_id)
    assert status.done and status.status == "completed"
    assert {r.custom_id for r in status.results} == {"insight-1", "insight-2"}
    assert all(r.output_json == _OUTPUT for r in status.results)

    # Idempotent: poll lại vẫn ra completed (không xóa khi đọc) để re-poll an toàn.
    again = await client.poll_batch(batch_id)
    assert again.done and {r.custom_id for r in again.results} == {"insight-1", "insight-2"}

    # Không có batch_id -> in_progress (chưa submit xong hoặc hết TTL).
    missing = await client.poll_batch("orbatch_unknown")
    assert missing.status == "in_progress" and not missing.done


def test_parse_output_text_rejects_non_dict() -> None:
    assert _parse_output_text("[1,2]") is None
    assert _parse_output_text("not json") is None
    assert _parse_output_text('{"x":1}') == {"x": 1}
