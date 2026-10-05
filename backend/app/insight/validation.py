"""Kiểm tra bằng chứng sau khi nhận đầu ra AI (spec mục 8): mọi `evidence.ref` phải tồn tại
trong đầu vào và `kind` phải khớp loại ref; khoảng ngày phải nằm trong kỳ và `date_from` ≤
`date_to`; highlight phải nêu khách sạn. Mục nào không hợp lệ bị loại và ghi vào
`dropped_highlights` kèm lý do."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.insight.schema import InsightOutput

# evidence.kind -> tiền tố ref hợp lệ (khớp input_builder và schema.Evidence).
REF_PREFIX_BY_KIND = {
    "event": "evt:",
    "metric": "metric:",
    "compset": "compset:",
    "demand": "demand:",
}


@dataclass
class ValidationResult:
    output: dict[str, Any]
    dropped: list[dict[str, Any]] = field(default_factory=list)
    parse_error: str | None = None


def _evidence_reasons(evidence: list[dict[str, Any]], valid_refs: set[str]) -> list[str]:
    reasons = []
    if not evidence:
        reasons.append("no evidence")
    bad = [e.get("ref", "") for e in evidence if e.get("ref") not in valid_refs]
    if bad:
        reasons.append(f"unknown refs: {bad}")
    # Sau pydantic, `kind` luôn là một trong các khoá của REF_PREFIX_BY_KIND.
    mismatched = [
        f"{e['kind']}:{e['ref']}"
        for e in evidence
        if not e["ref"].startswith(REF_PREFIX_BY_KIND[e["kind"]])
    ]
    if mismatched:
        reasons.append(f"kind/ref mismatch: {mismatched}")
    return reasons


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _bad_dates(*values: str, start: date, end: date) -> list[str]:
    bad = []
    for v in values:
        d = _parse_date(v)
        if d is None or not (start <= d <= end):
            bad.append(v)
    return bad


def _range_reasons(date_from: str, date_to: str, start: date, end: date) -> list[str]:
    reasons = []
    bad = _bad_dates(date_from, date_to, start=start, end=end)
    if bad:
        reasons.append(f"dates outside period: {bad}")
    d1, d2 = _parse_date(date_from), _parse_date(date_to)
    if d1 is not None and d2 is not None and d1 > d2:
        reasons.append(f"date_from after date_to: {date_from} > {date_to}")
    return reasons


def validate_output(
    raw: dict[str, Any],
    valid_refs: set[str],
    period_start: date,
    period_end: date,
    known_hotel_ids: set[int],
) -> ValidationResult:
    try:
        parsed = InsightOutput.model_validate(raw)
    except ValidationError as exc:
        return ValidationResult(output={}, parse_error=str(exc)[:2000])
    out = parsed.model_dump()
    dropped: list[dict[str, Any]] = []

    def keep(section: str, item: dict[str, Any], reasons: list[str]) -> bool:
        if reasons:
            dropped.append({"section": section, "item": item, "reasons": reasons})
            return False
        return True

    kept_highlights = []
    for h in out["highlights"]:
        reasons = _evidence_reasons(h["evidence"], valid_refs)
        if not h["hotel_ids"]:
            reasons.append("no hotel_ids")
        unknown_hotels = [i for i in h["hotel_ids"] if i not in known_hotel_ids]
        if unknown_hotels:
            reasons.append(f"unknown hotel_ids: {unknown_hotels}")
        reasons += _range_reasons(h["date_from"], h["date_to"], period_start, period_end)
        if keep("highlights", h, reasons):
            kept_highlights.append(h)
    out["highlights"] = kept_highlights

    kept_ops = []
    for p in out["pricing_opportunities"]:
        reasons = _evidence_reasons(p["evidence"], valid_refs)
        reasons += _range_reasons(p["date_from"], p["date_to"], period_start, period_end)
        if keep("pricing_opportunities", p, reasons):
            kept_ops.append(p)
    out["pricing_opportunities"] = kept_ops

    kept_risks = []
    for r in out["risks"]:
        if keep("risks", r, _evidence_reasons(r["evidence"], valid_refs)):
            kept_risks.append(r)
    out["risks"] = kept_risks

    kept_signals = []
    for s in out["demand_signals"]:
        reasons = []
        bad_dates = _bad_dates(s["date"], start=period_start, end=period_end)
        if bad_dates:
            reasons.append(f"date outside period: {bad_dates}")
        if keep("demand_signals", s, reasons):
            kept_signals.append(s)
    out["demand_signals"] = kept_signals

    return ValidationResult(output=out, dropped=dropped)
