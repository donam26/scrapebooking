"""Bộ 10 kịch bản với kỳ vọng xác định (spec mục 8, 12).

Mỗi kịch bản là một file JSON trong tests/fixtures/insight/: đầu vào tối giản (tập ref hợp
lệ, khách sạn, kỳ) + đầu ra mô phỏng của model + kỳ vọng sau kiểm tra bằng chứng.
Đổi PROMPT_VERSION hay quy tắc kiểm tra thì chạy lại bộ này.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.insight.client import CompletionRequest, estimate_cost
from app.insight.prompt import PROMPT_VERSION, SYSTEM_PROMPT, user_prompt
from app.insight.schema import INSIGHT_JSON_SCHEMA
from app.insight.validation import validate_output

SCENARIOS = sorted((Path(__file__).parent.parent / "fixtures" / "insight").glob("*.json"))


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario(path: Path) -> None:
    sc = json.loads(path.read_text(encoding="utf-8"))
    res = validate_output(
        sc["model_output"],
        set(sc["valid_refs"]),
        date.fromisoformat(sc["period"]["start"]),
        date.fromisoformat(sc["period"]["end"]),
        set(sc["hotel_ids"]),
    )
    exp = sc["expected"]
    if exp.get("parse_error"):
        assert res.parse_error is not None
        return
    assert res.parse_error is None
    assert len(res.output["highlights"]) == exp["highlights_kept"]
    assert len(res.output["pricing_opportunities"]) == exp["pricing_kept"]
    assert len(res.output["risks"]) == exp["risks_kept"]
    assert len(res.output["demand_signals"]) == exp["signals_kept"]
    assert len(res.dropped) == exp["dropped"]
    for needle in exp.get("dropped_reasons_contain", []):
        assert any(needle in r for d in res.dropped for r in d["reasons"]), needle
    assert res.output["summary"] == sc["model_output"]["summary"]


def test_ten_scenarios_present() -> None:
    assert len(SCENARIOS) >= 10


def test_request_body_uses_structured_outputs_and_fixed_system_prompt() -> None:
    req = CompletionRequest(
        "insight-1", "gpt-6-luna", SYSTEM_PROMPT, user_prompt("vi"), {"a": 1}, "medium"
    )
    body = req.body()
    assert body["model"] == "gpt-6-luna" and body["reasoning"] == {"effort": "medium"}
    assert body["input"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert body["input"][1]["content"].endswith('{"a":1}')
    fmt = body["text"]["format"]
    assert (
        fmt["type"] == "json_schema"
        and fmt["strict"] is True
        and fmt["schema"] == INSIGHT_JSON_SCHEMA
    )
    assert PROMPT_VERSION == "1"


def test_cost_estimate_matches_research_pricing() -> None:
    # 20.000 token vào, 2.000 token ra: 0.002 + 0.001 = $0.003, batch còn $0.0015
    assert str(estimate_cost(20_000, 2_000)) == "0.003000"
    assert str(estimate_cost(20_000, 2_000, batch=True)) == "0.001500"
