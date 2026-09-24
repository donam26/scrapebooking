"""Kiểm tra bằng chứng sau khi nhận đầu ra AI (spec mục 8): mọi `evidence.ref` phải tồn tại
trong đầu vào; mục nào không hợp lệ bị loại và ghi vào `dropped_highlights`."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.insight.schema import InsightOutput


@dataclass
class ValidationResult:
    output: dict[str, Any]
    dropped: list[dict[str, Any]] = field(default_factory=list)
    parse_error: str | None = None


def _bad_refs(evidence: list[dict[str, Any]], valid_refs: set[str]) -> list[str]:
    return [e.get("ref", "") for e in evidence if e.get("ref") not in valid_refs]


def _bad_dates(*values: str, start: date, end: date) -> list[str]:
    bad = []
    for v in values:
        try:
            d = date.fromisoformat(v)
        except ValueError:
            bad.append(v)
            continue
        if not (start <= d <= end):
            bad.append(v)
    return bad


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
        reasons = []
        if not h["evidence"]:
            reasons.append("no evidence")
        bad = _bad_refs(h["evidence"], valid_refs)
        if bad:
            reasons.append(f"unknown refs: {bad}")
        unknown_hotels = [i for i in h["hotel_ids"] if i not in known_hotel_ids]
        if unknown_hotels:
            reasons.append(f"unknown hotel_ids: {unknown_hotels}")
        bad_dates = _bad_dates(h["date_from"], h["date_to"], start=period_start, end=period_end)
        if bad_dates:
            reasons.append(f"dates outside period: {bad_dates}")
        if keep("highlights", h, reasons):
            kept_highlights.append(h)
    out["highlights"] = kept_highlights

    kept_ops = []
    for p in out["pricing_opportunities"]:
        reasons = []
        if not p["evidence"]:
            reasons.append("no evidence")
        bad = _bad_refs(p["evidence"], valid_refs)
        if bad:
            reasons.append(f"unknown refs: {bad}")
        bad_dates = _bad_dates(p["date_from"], p["date_to"], start=period_start, end=period_end)
        if bad_dates:
            reasons.append(f"dates outside period: {bad_dates}")
        if keep("pricing_opportunities", p, reasons):
            kept_ops.append(p)
    out["pricing_opportunities"] = kept_ops

    kept_risks = []
    for r in out["risks"]:
        reasons = []
        if not r["evidence"]:
            reasons.append("no evidence")
        bad = _bad_refs(r["evidence"], valid_refs)
        if bad:
            reasons.append(f"unknown refs: {bad}")
        if keep("risks", r, reasons):
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
