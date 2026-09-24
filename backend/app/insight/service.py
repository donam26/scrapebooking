"""InsightService: sinh bản tin hằng ngày (Batch API) và theo yêu cầu (đồng bộ)."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Insight, Tenant
from app.insight.client import (
    CompletionRequest,
    CompletionResult,
    FakeInsightClient,
    InsightClient,
    OpenAIInsightClient,
    estimate_cost,
)
from app.insight.input_builder import InsightInput, build_input
from app.insight.prompt import PROMPT_VERSION, SYSTEM_PROMPT, user_prompt
from app.insight.validation import validate_output
from app.logging import get_logger
from app.ops.metrics import INSIGHTS_TOTAL

log = get_logger(__name__)


def build_openai_client(settings: Settings) -> InsightClient:
    if not settings.openai_api_key:
        log.warning("openai_api_key_missing_using_fake_client")
        return FakeInsightClient(
            default_output={
                "summary": "OPENAI_API_KEY chưa cấu hình; đây là đầu ra giả.",
                "highlights": [],
                "demand_signals": [],
                "pricing_opportunities": [],
                "risks": [],
                "data_quality_note": "fake client",
            }
        )
    return OpenAIInsightClient(settings.openai_api_key)


@dataclass(frozen=True)
class DueTenant:
    tenant_id: int
    request_key: str  # daily:<local date>


def due_daily_tenants(tenants: list[Tenant], now: datetime, lookback: timedelta) -> list[DueTenant]:
    """Tenant có insight_hour (giờ địa phương) rơi vào (now - lookback, now]."""
    out = []
    for t in tenants:
        tz = ZoneInfo(t.timezone)
        hh, mm = (int(x) for x in t.insight_hour.split(":"))
        local_today = now.astimezone(tz).date()
        for offset in (0, -1):
            d = local_today + timedelta(days=offset)
            at = datetime.combine(d, time(hh, mm), tzinfo=tz).astimezone(UTC)
            if now - lookback < at <= now:
                out.append(DueTenant(t.id, f"daily:{d.isoformat()}"))
    return out


class InsightService:
    def __init__(self, session: AsyncSession, client: InsightClient, settings: Settings) -> None:
        self._s = session
        self._client = client
        self._settings = settings

    def _request(self, insight_id: int, built: InsightInput, language: str) -> CompletionRequest:
        return CompletionRequest(
            custom_id=f"insight-{insight_id}",
            model=self._settings.openai_model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt(language),
            input_json=built.payload,
            reasoning_effort=self._settings.openai_reasoning_effort,
        )

    async def _find_pending(self, tenant_id: int, request_key: str | None) -> Insight | None:
        if request_key and request_key.startswith("req"):
            row = await self._s.get(Insight, int(request_key[3:]))
            if row is not None and row.tenant_id == tenant_id and row.status == "pending":
                return row
        return None

    async def _already_done(self, tenant_id: int, request_key: str | None) -> Insight | None:
        """Bản tin hằng ngày idempotent theo (tenant, ngày địa phương)."""
        if not request_key or not request_key.startswith("daily:"):
            return None
        day = request_key.split(":", 1)[1]
        rows = (
            (
                await self._s.execute(
                    select(Insight).where(
                        Insight.tenant_id == tenant_id,
                        Insight.trigger == "daily",
                        Insight.period_start == datetime.fromisoformat(day).date(),
                        Insight.status.in_(["completed", "batch_pending"]),
                    )
                )
            )
            .scalars()
            .first()
        )
        return rows

    async def generate(
        self,
        tenant_id: int,
        trigger: str,
        use_batch: bool,
        request_key: str | None = None,
        now: datetime | None = None,
    ) -> Insight:
        now = now or datetime.now(tz=UTC)
        tenant = await self._s.get(Tenant, tenant_id)
        if tenant is None:
            raise ValueError(f"tenant {tenant_id} not found")
        done = await self._already_done(tenant_id, request_key)
        if done is not None:
            log.info("insight_already_generated", tenant=tenant_id, key=request_key)
            return done

        built = await build_input(self._s, tenant, now)
        row = await self._find_pending(tenant_id, request_key)
        if row is None:
            row = Insight(
                tenant_id=tenant_id,
                period_start=built.period_start,
                period_end=built.period_end,
                generated_at=now,
                trigger=trigger,
                status="pending",
                model=self._settings.openai_model,
                prompt_version=PROMPT_VERSION,
                input_json={},
                output_json=None,
                dropped_highlights=[],
            )
            self._s.add(row)
            await self._s.flush()
        row.period_start, row.period_end = built.period_start, built.period_end
        row.scan_run_id = built.scan_run_id
        row.input_json = built.payload
        row.model = self._settings.openai_model
        row.prompt_version = PROMPT_VERSION

        if not built.hotel_ids:
            row.status, row.error = "failed", "watchlist is empty"
            INSIGHTS_TOTAL.labels("failed").inc()
            await self._s.flush()
            return row

        request = self._request(row.id, built, tenant.insight_language)
        if use_batch:
            row.batch_id = await self._client.submit_batch([request])
            row.status = "batch_pending"
            INSIGHTS_TOTAL.labels("batch_pending").inc()
            await self._s.flush()
            return row

        result = await self._client.complete(request)
        self._apply_result(row, built, result, batch=False)
        await self._s.flush()
        return row

    def _apply_result(
        self, row: Insight, built: InsightInput, result: CompletionResult, batch: bool
    ) -> None:
        row.tokens_in, row.tokens_out = result.tokens_in, result.tokens_out
        row.cost_usd = estimate_cost(result.tokens_in, result.tokens_out, batch=batch)
        if result.error or result.output_json is None:
            row.status = "failed"
            row.error = result.error or "no json output"
            INSIGHTS_TOTAL.labels("failed").inc()
            log.warning("insight_failed", insight_id=row.id, error=row.error)
            return
        validated = validate_output(
            result.output_json,
            built.valid_refs,
            built.period_start,
            built.period_end,
            built.hotel_ids,
        )
        if validated.parse_error:
            row.status = "failed"
            row.error = f"schema: {validated.parse_error}"
            INSIGHTS_TOTAL.labels("failed").inc()
            return
        row.output_json = validated.output
        row.dropped_highlights = validated.dropped
        row.status = "completed"
        row.error = None
        INSIGHTS_TOTAL.labels("completed").inc()
        log.info(
            "insight_completed",
            insight_id=row.id,
            highlights=len(validated.output["highlights"]),
            dropped=len(validated.dropped),
            cost_usd=str(row.cost_usd),
        )

    async def poll_batches(self) -> int:
        """Hoàn tất các bản tin đang chờ Batch API. Trả về số bản tin cập nhật."""
        pending = (
            (
                await self._s.execute(
                    select(Insight).where(
                        Insight.status == "batch_pending", Insight.batch_id.is_not(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        by_batch: dict[str, list[Insight]] = {}
        for row in pending:
            assert row.batch_id is not None
            by_batch.setdefault(row.batch_id, []).append(row)
        updated = 0
        for batch_id, rows in by_batch.items():
            status = await self._client.poll_batch(batch_id)
            if not status.done:
                continue
            results = {r.custom_id: r for r in status.results}
            for row in rows:
                result = results.get(f"insight-{row.id}")
                if result is None:
                    result = CompletionResult(
                        f"insight-{row.id}", None, error=f"batch {status.status} without result"
                    )
                built = _rebuild_from_stored(row)
                self._apply_result(row, built, result, batch=True)
                updated += 1
        await self._s.flush()
        return updated


def _rebuild_from_stored(row: Insight) -> InsightInput:
    """Dựng lại tập ref hợp lệ từ input_json đã lưu để kiểm tra bằng chứng khi batch về."""
    payload: dict[str, Any] = row.input_json or {}
    refs: set[str] = set()
    hotel_ids: set[int] = set()
    for h in payload.get("hotels", []):
        hotel_ids.add(int(h["hotel_id"]))
        for d in h.get("days", []):
            if d.get("status") != "no_data":
                refs.add(d["ref"])
    for key in ("events_24h", "events_7d", "compset"):
        for item in payload.get(key, []):
            refs.add(item["ref"])
    return InsightInput(payload, refs, hotel_ids, row.period_start, row.period_end, row.scan_run_id)
