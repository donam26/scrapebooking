from datetime import date

from app.insight.validation import validate_output

START, END = date(2026, 10, 1), date(2026, 10, 30)
REFS = {"metric:1:2026-10-05", "evt:10", "compset:2026-10-05", "demand:7"}
HOTELS = {1, 2}


def _out(**overrides):  # type: ignore[no-untyped-def]
    base = {
        "summary": "ok",
        "highlights": [],
        "demand_signals": [],
        "pricing_opportunities": [],
        "risks": [],
        "data_quality_note": "",
    }
    base.update(overrides)
    return base


def _kind(ref: str) -> str:
    return {"evt": "event", "metric": "metric", "compset": "compset", "demand": "demand"}[
        ref.split(":", 1)[0]
    ]


def _h(
    refs: list[str],
    hotel_ids: list[int] | None = None,
    d1: str = "2026-10-05",
    d2: str = "2026-10-05",
    evidence: list[dict[str, str]] | None = None,
):  # type: ignore[no-untyped-def]
    return {
        "title": "t",
        "date_from": d1,
        "date_to": d2,
        "hotel_ids": [1] if hotel_ids is None else hotel_ids,
        "evidence": evidence
        if evidence is not None
        else [{"kind": _kind(r), "ref": r} for r in refs],
        "confidence": "high",
        "recommendation": "r",
    }


def test_valid_output_kept_untouched() -> None:
    res = validate_output(
        _out(highlights=[_h(["evt:10", "metric:1:2026-10-05", "demand:7"])]),
        REFS,
        START,
        END,
        HOTELS,
    )
    assert res.parse_error is None and res.dropped == []
    assert len(res.output["highlights"]) == 1


def test_unknown_ref_drops_highlight_and_records_reason() -> None:
    res = validate_output(
        _out(highlights=[_h(["evt:999"]), _h(["evt:10"])]), REFS, START, END, HOTELS
    )
    assert len(res.output["highlights"]) == 1
    assert len(res.dropped) == 1 and "unknown refs" in res.dropped[0]["reasons"][0]
    assert res.dropped[0]["section"] == "highlights"


def test_no_evidence_is_dropped() -> None:
    res = validate_output(_out(highlights=[_h([])]), REFS, START, END, HOTELS)
    assert res.output["highlights"] == [] and res.dropped[0]["reasons"] == ["no evidence"]


def test_kind_must_match_ref_prefix() -> None:
    # ref có thật nhưng kind sai -> loại; không lọt vì "unknown refs" không bắt được.
    wrong = [{"kind": "metric", "ref": "evt:10"}, {"kind": "event", "ref": "demand:7"}]
    res = validate_output(
        _out(
            highlights=[_h([], evidence=wrong), _h(["demand:7"])],
            risks=[
                {"title": "r", "rationale": "x", "evidence": [{"kind": "demand", "ref": "evt:10"}]}
            ],
        ),
        REFS,
        START,
        END,
        HOTELS,
    )
    assert len(res.output["highlights"]) == 1 and res.output["risks"] == []
    assert len(res.dropped) == 2
    reasons = res.dropped[0]["reasons"]
    assert reasons == ["kind/ref mismatch: ['metric:evt:10', 'event:demand:7']"]
    assert "kind/ref mismatch" in res.dropped[1]["reasons"][0]


def test_date_from_after_date_to_is_dropped() -> None:
    res = validate_output(
        _out(
            highlights=[_h(["evt:10"], d1="2026-10-06", d2="2026-10-05")],
            pricing_opportunities=[
                {
                    "date_from": "2026-10-07",
                    "date_to": "2026-10-05",
                    "rationale": "x",
                    "evidence": [{"kind": "compset", "ref": "compset:2026-10-05"}],
                }
            ],
        ),
        REFS,
        START,
        END,
        HOTELS,
    )
    assert res.output["highlights"] == [] and res.output["pricing_opportunities"] == []
    assert [d["reasons"] for d in res.dropped] == [
        ["date_from after date_to: 2026-10-06 > 2026-10-05"],
        ["date_from after date_to: 2026-10-07 > 2026-10-05"],
    ]


def test_highlight_without_hotel_ids_is_dropped() -> None:
    res = validate_output(_out(highlights=[_h(["evt:10"], hotel_ids=[])]), REFS, START, END, HOTELS)
    assert res.output["highlights"] == [] and res.dropped[0]["reasons"] == ["no hotel_ids"]


def test_unknown_hotel_and_dates_outside_period() -> None:
    res = validate_output(
        _out(
            highlights=[
                _h(["evt:10"], hotel_ids=[9]),
                _h(["evt:10"], d1="2026-12-01", d2="2026-12-02"),
            ]
        ),
        REFS,
        START,
        END,
        HOTELS,
    )
    assert res.output["highlights"] == []
    reasons = [r["reasons"] for r in res.dropped]
    assert any("unknown hotel_ids" in x[0] for x in reasons)
    assert any("dates outside period" in x[0] for x in reasons)


def test_pricing_risks_signals_validation() -> None:
    out = _out(
        pricing_opportunities=[
            {
                "date_from": "2026-10-05",
                "date_to": "2026-10-06",
                "rationale": "x",
                "evidence": [{"kind": "compset", "ref": "compset:2026-10-05"}],
            },
            {"date_from": "2026-10-05", "date_to": "2026-10-06", "rationale": "x", "evidence": []},
        ],
        risks=[
            {
                "title": "r",
                "rationale": "x",
                "evidence": [{"kind": "metric", "ref": "metric:1:2026-10-05"}],
            },
            {
                "title": "r2",
                "rationale": "x",
                "evidence": [{"kind": "metric", "ref": "metric:1:2026-10-99"}],
            },
        ],
        demand_signals=[
            {"date": "2026-10-05", "level": "high", "reason": "x"},
            {"date": "2026-11-05", "level": "high", "reason": "x"},
            {"date": "not-a-date", "level": "low", "reason": "x"},
        ],
    )
    res = validate_output(out, REFS, START, END, HOTELS)
    assert len(res.output["pricing_opportunities"]) == 1
    assert len(res.output["risks"]) == 1
    assert len(res.output["demand_signals"]) == 1
    assert len(res.dropped) == 4


def test_schema_violation_is_parse_error() -> None:
    res = validate_output(
        {"summary": "x"}, REFS, START, END, HOTELS
    )  # thiếu data_quality_note là ok (default)
    assert res.parse_error is None
    res = validate_output({"highlights": "nope"}, REFS, START, END, HOTELS)
    assert res.parse_error is not None and res.output == {}
