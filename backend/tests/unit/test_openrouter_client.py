"""Unit test cho OpenRouterInsightClient: shape request Chat Completions, giới hạn mỗi lần gọi
(max_tokens, timeout, số lần thử lại), parse kết quả và ước lượng token khi thiếu usage."""

import json
from types import SimpleNamespace
from typing import Any

import pytest

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
_USAGE = SimpleNamespace(prompt_tokens=123, completion_tokens=45)


class _FakeCompletions:
    def __init__(self, content: str, calls: list[dict[str, Any]], usage: Any) -> None:
        self._content = content
        self._calls = calls
        self._usage = usage

    async def create(self, **kwargs: Any) -> Any:
        self._calls.append(kwargs)
        if isinstance(self._content, Exception):
            raise self._content
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=self._usage,
        )


class _FakeAsyncOpenAI:
    def __init__(self, content: Any, usage: Any = _USAGE) -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=_FakeCompletions(content, self.calls, usage))


def _request(custom_id: str = "insight-1") -> CompletionRequest:
    return CompletionRequest(custom_id, "openai/gpt-6-luna", "SYS", "USER:", {"a": 1}, "high")


async def test_complete_shapes_chat_completions_and_parses() -> None:
    fake = _FakeAsyncOpenAI(json.dumps(_OUTPUT))
    client = OpenRouterInsightClient(client=fake, max_output_tokens=2048)

    result = await client.complete(_request())

    assert result.output_json == _OUTPUT
    assert result.tokens_in == 123 and result.tokens_out == 45 and result.error is None
    call = fake.calls[0]
    assert call["model"] == "openai/gpt-6-luna"
    assert call["messages"][0] == {"role": "system", "content": "SYS"}
    assert call["messages"][1]["content"].endswith('{"a":1}')
    assert call["response_format"]["json_schema"]["schema"] == INSIGHT_JSON_SCHEMA
    assert call["extra_body"] == {"reasoning": {"effort": "high"}}
    assert call["max_tokens"] == 2048


async def test_complete_empty_content_is_error() -> None:
    client = OpenRouterInsightClient(client=_FakeAsyncOpenAI(""))
    result = await client.complete(_request())
    assert result.output_json is None and result.error == "empty response"


async def test_complete_without_usage_stores_estimated_tokens_in() -> None:
    client = OpenRouterInsightClient(client=_FakeAsyncOpenAI(json.dumps(_OUTPUT), usage=None))
    req = _request()
    result = await client.complete(req)
    assert result.output_json == _OUTPUT and result.error is None
    assert result.tokens_in == req.estimated_input_tokens > 0
    assert result.tokens_out == 0


async def test_complete_exception_returns_error_with_estimate() -> None:
    client = OpenRouterInsightClient(client=_FakeAsyncOpenAI(RuntimeError("boom")))
    req = _request()
    result = await client.complete(req)
    assert result.output_json is None and result.error == "RuntimeError: boom"
    assert result.tokens_in == req.estimated_input_tokens


def test_estimated_input_tokens_counts_all_messages() -> None:
    req = _request()
    chars = len("SYS") + len("USER:" + '{"a":1}')
    assert req.estimated_input_tokens == chars // 4


def test_sdk_client_gets_timeout_and_single_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    class _Recording:
        def __init__(self, **kwargs: Any) -> None:
            created.update(kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", _Recording)
    OpenRouterInsightClient(
        api_key="k", headers={"X-Title": "t"}, timeout_seconds=45.0, max_retries=1
    )
    assert created["timeout"] == 45.0 and created["max_retries"] == 1
    assert created["api_key"] == "k" and created["default_headers"] == {"X-Title": "t"}


def test_parse_output_text_rejects_non_dict() -> None:
    assert _parse_output_text("[1,2]") is None
    assert _parse_output_text("not json") is None
    assert _parse_output_text('{"x":1}') == {"x": 1}
