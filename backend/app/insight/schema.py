"""Schema đầu ra Structured Outputs (spec mục 8) và model pydantic để kiểm tra."""

from typing import Any, Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]
Level = Literal["high", "medium", "low"]


class Evidence(BaseModel):
    kind: Literal["event", "metric", "compset"]
    ref: str


class Highlight(BaseModel):
    title: str
    date_from: str
    date_to: str
    hotel_ids: list[int]
    evidence: list[Evidence]
    confidence: Confidence
    recommendation: str


class DemandSignal(BaseModel):
    date: str
    level: Level
    reason: str


class PricingOpportunity(BaseModel):
    date_from: str
    date_to: str
    rationale: str
    evidence: list[Evidence]


class Risk(BaseModel):
    title: str
    rationale: str
    evidence: list[Evidence]


class InsightOutput(BaseModel):
    summary: str
    highlights: list[Highlight] = Field(default_factory=list)
    demand_signals: list[DemandSignal] = Field(default_factory=list)
    pricing_opportunities: list[PricingOpportunity] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    data_quality_note: str = ""


_EVIDENCE = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["event", "metric", "compset"]},
        "ref": {"type": "string"},
    },
    "required": ["kind", "ref"],
    "additionalProperties": False,
}

INSIGHT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "highlights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "hotel_ids": {"type": "array", "items": {"type": "integer"}},
                    "evidence": {"type": "array", "items": _EVIDENCE},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "recommendation": {"type": "string"},
                },
                "required": [
                    "title",
                    "date_from",
                    "date_to",
                    "hotel_ids",
                    "evidence",
                    "confidence",
                    "recommendation",
                ],
                "additionalProperties": False,
            },
        },
        "demand_signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "level": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reason": {"type": "string"},
                },
                "required": ["date", "level", "reason"],
                "additionalProperties": False,
            },
        },
        "pricing_opportunities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "rationale": {"type": "string"},
                    "evidence": {"type": "array", "items": _EVIDENCE},
                },
                "required": ["date_from", "date_to", "rationale", "evidence"],
                "additionalProperties": False,
            },
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "evidence": {"type": "array", "items": _EVIDENCE},
                },
                "required": ["title", "rationale", "evidence"],
                "additionalProperties": False,
            },
        },
        "data_quality_note": {"type": "string"},
    },
    "required": [
        "summary",
        "highlights",
        "demand_signals",
        "pricing_opportunities",
        "risks",
        "data_quality_note",
    ],
    "additionalProperties": False,
}
