"""Nhịp đặt phòng và gợi ý giá (đợt 2). Schema nằm trong file này để module tự đứng riêng."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert

from app.analytics.compset import load_compset
from app.analytics.rules import median
from app.api.deps import LocaleDep, SessionDep, SettingsDep, TenantDep, WriterDep
from app.api.hotel_views import tenant_channel
from app.api.schemas import HolidayOut
from app.db.models import Hotel, HotelDateSnapshot, OwnHotelDaily, Tenant, TenantHotel
from app.holidays.data import holidays_between
from app.i18n import t
from app.logging import get_logger
from app.market.models import LocalEvent, OtbSnapshot, PriceStrategy, PriceSuggestionDecision
from app.market.pace_report import (
    NightReport,
    PaceReport,
    build_pace_report,
    latest_observations,
    strategy_from,
    tenant_today,
    typical_index,
)
from app.market.pacing import Pace
from app.market.price_suggest import (
    NightSignals,
    Suggestion,
    backtest_verdict,
    reason_text,
    suggest,
)
from app.market.weather import WeatherUnavailable, fetch_weather

router = APIRouter(prefix="/market", tags=["market"])
log = get_logger(__name__)

MAX_RANGE_DAYS = 60
DEFAULT_DAYS = 30
MAX_HOLIDAY_DAYS = 400


class OccOut(BaseModel):
    """Công suất ước tính một lần quét: khoảng [thấp, cao] và độ phủ (phần biết chắc)."""

    occ_low: Decimal
    occ_high: Decimal
    occ_mid: Decimal
    coverage: Decimal
    reliable: bool
    status: str
    inventory: int
    days_to_arrival: int


class PaceOut(BaseModel):
    reference: Decimal | None
    references: int
    delta: Decimal | None


class ReasonOut(BaseModel):
    key: str
    text: str
    pct: int | None  # đóng góp % vào giá mục tiêu (null = thông tin/chặn)


class SuggestionOut(BaseModel):
    kind: Literal["raise", "hold", "lower"]
    change_pct: int
    confidence: Literal["high", "medium", "low"]
    reasons: list[str]
    decision: Literal["applied", "dismissed"] | None
    # RMS-lite (Phase 6): giá mục tiêu VND, giá tham chiếu, từng điều chỉnh có số, gợi ý hạn chế.
    target_price: Decimal | None = None
    reference_price: Decimal | None = None
    adjustments: list[ReasonOut] = []
    restrictions: list[str] = []
    clamped: str | None = None


class PaceNightOut(BaseModel):
    stay_date: date
    days_to_arrival: int
    holiday: str | None
    own_occ: OccOut | None
    own_pms_occ: Decimal | None
    own_pace: PaceOut
    own_price: Decimal | None
    own_status: str | None
    own_rooms_left: int | None
    currency: str | None
    comp_observed: int
    comp_sold_out: int
    comp_median_price: Decimal | None
    comp_occ: Decimal | None
    comp_occ_hotels: int
    # Khoảng [thấp, cao] của chỉ báo lấp đầy đối thủ (trung vị cận dưới/cận trên), 1.3.
    comp_occ_low: Decimal | None = None
    comp_occ_high: Decimal | None = None
    # Số đối thủ có giá 1 đêm còn bán (n) để so trung vị.
    comp_priced: int = 0
    comp_pickup_7d: int | None
    comp_pickup_hotels: int
    comp_pace: PaceOut
    suggestion: SuggestionOut | None


class LeadCalibrationOut(BaseModel):
    bucket: str  # "0-7" | "8-30" | "31-90" (số ngày trước khi đến)
    nights: int
    mean_abs_error_pts: Decimal | None
    bias_pts: Decimal | None
    mape_pct: Decimal | None
    usable: bool  # sai số ≤ ngưỡng: được hiện chỉ báo ở nhóm lead time này


class CalibrationOut(BaseModel):
    nights: int
    mean_abs_error_pts: Decimal | None
    bias_pts: Decimal | None
    # "calibrated" khi có PMS để so; "uncalibrated" = chưa hiệu chỉnh (chưa nhập PMS).
    status: Literal["calibrated", "uncalibrated"] = "uncalibrated"
    by_lead: list[LeadCalibrationOut] = []


class MarketPaceOut(BaseModel):
    start: date
    end: date
    channel: str
    own_hotel_id: int | None
    own_hotel_ids: list[int] = []
    data_since: date | None
    calibration: CalibrationOut
    nights: list[PaceNightOut]


class WeatherNowOut(BaseModel):
    temp: float
    feels_like: float
    humidity: int
    description: str
    icon: str


class WeatherDayOut(BaseModel):
    date: date
    temp_min: float
    temp_max: float
    description: str
    icon: str
    pop: float


class WeatherOut(BaseModel):
    """`configured=False`: chưa đặt OPENWEATHER_API_KEY. `error`: có key nhưng chưa lấy được."""

    configured: bool
    location: str | None = None
    current: WeatherNowOut | None = None
    days: list[WeatherDayOut] = []
    error: str | None = None


class HotelOccNightOut(BaseModel):
    stay_date: date
    status: str
    inventory: int
    # Chỉ có khi ước tính đủ tin cậy (độ phủ ≥ 50%, khoảng hẹp); không thì null.
    occ_mid: Decimal | None
    reliable: bool


class HotelOccOut(BaseModel):
    hotel_id: int
    name: str | None
    role: str
    nights: list[HotelOccNightOut]


class MarketOccupancyOut(BaseModel):
    start: date
    end: date
    channel: str
    hotels: list[HotelOccOut]


EventCategory = Literal["festival", "mice", "sports", "season", "other"]
MAX_EVENT_DAYS = 120


class LocalEventIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: EventCategory
    start_date: date
    end_date: date
    # Mức tăng cầu người dùng dự kiến (%), không phải số đo được.
    expected_uplift_pct: int | None = Field(default=None, ge=-50, le=300)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _range(self) -> "LocalEventIn":
        if self.end_date < self.start_date:
            raise ValueError("end_date before start_date")
        if (self.end_date - self.start_date).days >= MAX_EVENT_DAYS:
            raise ValueError(f"event longer than {MAX_EVENT_DAYS} days")
        return self


class LocalEventOut(LocalEventIn):
    id: int


class DecisionIn(BaseModel):
    decision: Literal["applied", "dismissed"]
    # Giá thật sự đã đặt (khi khác giá mục tiêu); để đo kết quả sau đêm lưu trú.
    applied_price: Decimal | None = Field(default=None, gt=0)


class StrategyIn(BaseModel):
    base_price: Decimal | None = Field(default=None, gt=0)
    floor_price: Decimal | None = Field(default=None, gt=0)
    ceiling_price: Decimal | None = Field(default=None, gt=0)
    target_index: Decimal = Field(default=Decimal(100), ge=50, le=200)
    round_to: int = Field(default=10000, ge=0, le=1000000)
    max_daily_change_pct: int = Field(default=15, ge=1, le=50)
    weekday_adj: dict[int, int] = Field(default_factory=dict)
    holiday_uplift_pct: int = Field(default=10, ge=-30, le=50)
    last_minute_days: int = Field(default=3, ge=0, le=14)
    last_minute_adj_pct: int = Field(default=-5, ge=-30, le=0)

    @model_validator(mode="after")
    def _check(self) -> "StrategyIn":
        if self.floor_price and self.ceiling_price and self.floor_price > self.ceiling_price:
            raise ValueError("floor_price above ceiling_price")
        for k, v in self.weekday_adj.items():
            if not 0 <= k <= 6 or not -30 <= v <= 50:
                raise ValueError("weekday_adj: keys 0..6 (Mon..Sun), values -30..50")
        return self


class StrategyOut(StrategyIn):
    hotel_id: int
    configured: bool


class OutcomeNightOut(BaseModel):
    stay_date: date
    kind: str
    decision: str
    change_pct: int
    own_price: Decimal | None
    target_price: Decimal | None
    applied_price: Decimal | None
    actual_occ_pct: Decimal | None
    actual_adr: Decimal | None
    verdict: Literal["good", "review", "neutral", "pending"]


class OutcomesOut(BaseModel):
    """Nhật ký "gợi ý đã áp dụng → kết quả" (6.4) và tỷ lệ áp dụng."""

    decided: int
    applied: int
    dismissed: int
    apply_rate: Decimal | None
    good: int
    review: int
    nights: list[OutcomeNightOut]


class BacktestOut(BaseModel):
    """Chạy lại luật gợi ý trên giá đối thủ ~7 ngày trước mỗi đêm đã qua, so với công suất thật."""

    nights: int
    raise_nights: int
    lower_nights: int
    good: int
    review: int
    hit_rate: Decimal | None
    details: list[OutcomeNightOut]


def _pace(p: Pace) -> PaceOut:
    return PaceOut(reference=p.reference, references=p.references, delta=p.delta)


def _suggestion(s: Suggestion, decision: str | None, locale: str) -> SuggestionOut:
    return SuggestionOut(
        kind=s.kind,
        change_pct=s.change_pct,
        confidence=s.confidence,
        reasons=[reason_text(r, locale) for r in s.reasons],
        decision=decision,
        target_price=s.target_price,
        reference_price=s.reference_price,
        adjustments=[
            ReasonOut(key=r.key, text=reason_text(r, locale), pct=r.pct) for r in s.reasons
        ],
        restrictions=[reason_text(r, locale) for r in s.restrictions],
        clamped=s.clamped,
    )


def _night(n: NightReport, locale: str) -> PaceNightOut:
    o = n.own_obs
    return PaceNightOut(
        stay_date=n.stay_date,
        days_to_arrival=n.days_to_arrival,
        holiday=n.holiday,
        own_occ=OccOut(
            occ_low=o.occ_low,
            occ_high=o.occ_high,
            occ_mid=o.occ_mid,
            coverage=o.coverage,
            reliable=o.reliable,
            status=o.status,
            inventory=o.inventory,
            days_to_arrival=o.lead,
        )
        if o
        else None,
        own_pms_occ=n.own_pms_occ,
        own_pace=_pace(n.own_pace),
        own_price=n.own_price,
        own_status=n.own_status,
        own_rooms_left=n.own_rooms_left,
        currency=n.currency,
        comp_observed=n.comp_observed,
        comp_sold_out=n.comp_sold_out,
        comp_median_price=n.comp_median_price,
        comp_occ=n.comp_occ,
        comp_occ_hotels=n.comp_occ_hotels,
        comp_occ_low=n.comp_occ_low,
        comp_occ_high=n.comp_occ_high,
        comp_priced=n.comp_priced,
        comp_pickup_7d=n.comp_pickup_7d,
        comp_pickup_hotels=n.comp_pickup_hotels,
        comp_pace=_pace(n.comp_pace),
        suggestion=_suggestion(n.suggestion, n.decision, locale) if n.suggestion else None,
    )


def _out(r: PaceReport, locale: str) -> MarketPaceOut:
    return MarketPaceOut(
        start=r.start,
        end=r.end,
        channel=r.channel,
        own_hotel_id=r.own_hotel_id,
        own_hotel_ids=r.own_hotel_ids,
        data_since=r.data_since,
        calibration=CalibrationOut(
            nights=r.calibration.nights,
            mean_abs_error_pts=r.calibration.mean_abs_error_pts,
            bias_pts=r.calibration.bias_pts,
            status="calibrated" if any(c.nights for c in r.calibration_by_lead) else "uncalibrated",
            by_lead=[LeadCalibrationOut(**c.__dict__) for c in r.calibration_by_lead],
        ),
        nights=[_night(n, locale) for n in r.nights],
    )


async def _tenant(session: SessionDep, tenant_id: int) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    return tenant


@router.get("/pace", response_model=MarketPaceOut)
async def get_pace(
    tenant_id: TenantDep,
    session: SessionDep,
    locale: LocaleDep,
    start: date | None = None,
    end: date | None = None,
    own_hotel_id: int | None = None,
) -> MarketPaceOut:
    """Nhịp và chỉ báo lấp đầy theo đêm (Booking.com)."""
    tenant = await _tenant(session, tenant_id)
    today = tenant_today(tenant)
    s = start or today
    e = end or s + timedelta(days=DEFAULT_DAYS - 1)
    if abs((s - today).days) > 730 or e < s or (e - s).days >= MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"range must be 1–{MAX_RANGE_DAYS} nights"
        )
    report = await build_pace_report(
        session, tenant_id, s, e, today, locale, own_hotel_id=own_hotel_id
    )
    return _out(report, locale)


@router.put("/suggestions/{stay_date}/{kind}", response_model=SuggestionOut)
async def decide_suggestion(
    stay_date: date,
    kind: Literal["raise", "hold", "lower"],
    body: DecisionIn,
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    locale: LocaleDep,
) -> SuggestionOut:
    """Ghi nhận đã áp dụng hoặc bỏ qua gợi ý (tính lại tại chỗ, không tin số từ client)."""
    tenant = await _tenant(session, tenant_id)
    report = await build_pace_report(
        session, tenant_id, stay_date, stay_date, tenant_today(tenant), locale
    )
    night = report.nights[0]
    sug = night.suggestion
    if sug is None or sug.kind != kind:
        raise HTTPException(status.HTTP_409_CONFLICT, "no such suggestion for this night anymore")
    values = dict(
        tenant_id=tenant_id,
        stay_date=stay_date,
        kind=kind,
        decision=body.decision,
        change_pct=sug.change_pct,
        own_price=night.own_price,
        currency=night.currency,
        decided_by=principal.user_id,
        hotel_id=report.own_hotel_id,
        target_price=sug.target_price,
        applied_price=body.applied_price
        or (sug.target_price if body.decision == "applied" else None),
        reasons=[{"key": r.key, "params": r.params, "pct": r.pct} for r in sug.reasons],
    )
    await session.execute(
        insert(PriceSuggestionDecision)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[
                PriceSuggestionDecision.tenant_id,
                PriceSuggestionDecision.stay_date,
                PriceSuggestionDecision.kind,
            ],
            set_={k: v for k, v in values.items() if k not in ("tenant_id", "stay_date", "kind")},
        )
    )
    await session.commit()
    return _suggestion(sug, body.decision, locale)


@router.delete("/suggestions/{stay_date}/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def undo_decision(
    stay_date: date,
    kind: Literal["raise", "hold", "lower"],
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
) -> None:
    await session.execute(
        delete(PriceSuggestionDecision).where(
            PriceSuggestionDecision.tenant_id == tenant_id,
            PriceSuggestionDecision.stay_date == stay_date,
            PriceSuggestionDecision.kind == kind,
        )
    )
    await session.commit()


@router.get("/holidays", response_model=list[HolidayOut])
async def get_holidays(
    tenant_id: TenantDep,
    session: SessionDep,
    locale: LocaleDep,
    start: date | None = None,
    end: date | None = None,
) -> list[HolidayOut]:
    """Ngày lễ theo nước của tenant cho lịch sự kiện (mặc định từ đầu tháng này, 12 tháng)."""
    tenant = await _tenant(session, tenant_id)
    s = start or tenant_today(tenant).replace(day=1)
    e = end or s + timedelta(days=365)
    if e < s or (e - s).days > MAX_HOLIDAY_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"range must be 1–{MAX_HOLIDAY_DAYS} days"
        )
    return [
        HolidayOut(date=h.date, name=h.name, kind=h.kind, group=h.group)
        for h in holidays_between(
            tenant.country_code,
            s,
            e,
            locale,
            source_markets=tenant.source_markets or (),
            include_seasons=True,
        )
    ]


@router.get("/weather", response_model=WeatherOut)
async def get_weather(
    tenant_id: TenantDep, session: SessionDep, settings: SettingsDep, locale: LocaleDep
) -> WeatherOut:
    """Dự báo 5 ngày tại khách sạn của bạn (hoặc khách sạn đầu tiên có toạ độ trong watchlist)."""
    if not settings.openweather_api_key:
        return WeatherOut(configured=False)
    row = (
        await session.execute(
            select(Hotel.lat, Hotel.lng)
            .join(TenantHotel, TenantHotel.hotel_id == Hotel.id)
            .where(
                TenantHotel.tenant_id == tenant_id,
                TenantHotel.active.is_(True),
                Hotel.lat.is_not(None),
                Hotel.lng.is_not(None),
            )
            .order_by(case((TenantHotel.role == "self", 0), else_=1), Hotel.id)
            .limit(1)
        )
    ).first()
    if row is None:
        return WeatherOut(configured=True, error=t(locale, "weather.no_coordinates"))
    try:
        w = await fetch_weather(row.lat, row.lng, settings.openweather_api_key, lang=locale)
    except WeatherUnavailable as exc:
        log.warning("weather_fetch_failed", tenant_id=tenant_id, reason=str(exc))
        return WeatherOut(configured=True, error=t(locale, "weather.unavailable"))
    return WeatherOut(
        configured=True,
        location=w.location,
        current=WeatherNowOut(**w.current.__dict__) if w.current else None,
        days=[WeatherDayOut(**d.__dict__) for d in w.days],
    )


@router.get("/occupancy", response_model=MarketOccupancyOut)
async def get_occupancy(
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
) -> MarketOccupancyOut:
    """Chỉ báo lấp đầy (thử nghiệm) mới nhất của từng khách sạn trong watchlist theo đêm."""
    tenant = await _tenant(session, tenant_id)
    s = start or tenant_today(tenant)
    e = end or s + timedelta(days=DEFAULT_DAYS - 1)
    if e < s or (e - s).days >= MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"range must be 1–{MAX_RANGE_DAYS} nights"
        )
    channel = tenant_channel()
    links = (
        await session.execute(
            select(TenantHotel.hotel_id, TenantHotel.role, TenantHotel.label, Hotel.name)
            .join(Hotel, Hotel.id == TenantHotel.hotel_id)
            .where(TenantHotel.tenant_id == tenant_id, TenantHotel.active.is_(True))
            .order_by(case((TenantHotel.role == "self", 0), else_=1), Hotel.id)
        )
    ).all()
    obs = await latest_observations(session, [r.hotel_id for r in links], channel, s, e)
    return MarketOccupancyOut(
        start=s,
        end=e,
        channel=channel,
        hotels=[
            HotelOccOut(
                hotel_id=r.hotel_id,
                name=r.label or r.name,
                role=r.role,
                nights=[
                    HotelOccNightOut(
                        stay_date=d,
                        status=o.status,
                        inventory=o.inventory,
                        occ_mid=o.occ_mid if o.reliable else None,
                        reliable=o.reliable,
                    )
                    for d, o in sorted(obs.get(r.hotel_id, {}).items())
                ],
            )
            for r in links
        ],
    )


def _event_out(e: LocalEvent) -> LocalEventOut:
    return LocalEventOut(
        id=e.id,
        name=e.name,
        category=e.category,
        start_date=e.start_date,
        end_date=e.end_date,
        expected_uplift_pct=e.expected_uplift_pct,
        note=e.note,
    )


async def _own_event(session: SessionDep, tenant_id: int, event_id: int) -> LocalEvent:
    ev = await session.get(LocalEvent, event_id)
    if ev is None or ev.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event not found")
    return ev


@router.get("/events", response_model=list[LocalEventOut])
async def list_events(
    tenant_id: TenantDep,
    session: SessionDep,
    start: date | None = None,
    end: date | None = None,
) -> list[LocalEventOut]:
    """Sự kiện địa phương giao với khoảng [start, end] (mặc định từ đầu tháng này, 12 tháng)."""
    tenant = await _tenant(session, tenant_id)
    s = start or tenant_today(tenant).replace(day=1)
    e = end or s + timedelta(days=365)
    if e < s or (e - s).days > MAX_HOLIDAY_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"range must be 1–{MAX_HOLIDAY_DAYS} days"
        )
    rows = (
        await session.execute(
            select(LocalEvent)
            .where(
                LocalEvent.tenant_id == tenant_id,
                LocalEvent.end_date >= s,
                LocalEvent.start_date <= e,
            )
            .order_by(LocalEvent.start_date, LocalEvent.id)
        )
    ).scalars()
    return [_event_out(r) for r in rows]


@router.post("/events", response_model=LocalEventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: LocalEventIn, tenant_id: TenantDep, principal: WriterDep, session: SessionDep
) -> LocalEventOut:
    ev = LocalEvent(tenant_id=tenant_id, created_by=principal.user_id, **body.model_dump())
    session.add(ev)
    await session.commit()
    await session.refresh(ev)
    return _event_out(ev)


@router.put("/events/{event_id}", response_model=LocalEventOut)
async def update_event(
    event_id: int, body: LocalEventIn, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> LocalEventOut:
    ev = await _own_event(session, tenant_id, event_id)
    for k, v in body.model_dump().items():
        setattr(ev, k, v)
    await session.commit()
    await session.refresh(ev)
    return _event_out(ev)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: int, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> None:
    ev = await _own_event(session, tenant_id, event_id)
    await session.delete(ev)
    await session.commit()


# ---- RMS-lite: chiến lược, kết quả, backtest (Phase 6) ---------------------------------------


async def _own_hotel(session: SessionDep, tenant_id: int, own_hotel_id: int | None) -> int:
    w = await load_compset(session, tenant_id, own_hotel_id)
    hid = own_hotel_id if own_hotel_id in w.own else (w.own[0] if w.own else None)
    if hid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no own hotel (role=self) in watchlist")
    return hid


def _strategy_out(hid: int, row: PriceStrategy | None) -> StrategyOut:
    st = strategy_from(row)
    return StrategyOut(
        hotel_id=hid,
        configured=row is not None,
        base_price=st.base_price,
        floor_price=st.floor,
        ceiling_price=st.ceiling,
        target_index=st.target_index,
        round_to=st.round_to,
        max_daily_change_pct=st.max_daily_change_pct,
        weekday_adj=st.weekday_adj,
        holiday_uplift_pct=st.holiday_uplift_pct,
        last_minute_days=st.last_minute_days,
        last_minute_adj_pct=st.last_minute_adj_pct,
    )


@router.get("/strategy", response_model=StrategyOut)
async def get_strategy(
    tenant_id: TenantDep, session: SessionDep, own_hotel_id: int | None = None
) -> StrategyOut:
    """Chiến lược giá của khách sạn của bạn (6.1); chưa đặt thì trả mặc định (định vị 100)."""
    hid = await _own_hotel(session, tenant_id, own_hotel_id)
    return _strategy_out(hid, await session.get(PriceStrategy, (tenant_id, hid)))


@router.put("/strategy", response_model=StrategyOut)
async def put_strategy(
    body: StrategyIn,
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    own_hotel_id: int | None = None,
) -> StrategyOut:
    hid = await _own_hotel(session, tenant_id, own_hotel_id)
    values = body.model_dump()
    values["weekday_adj"] = {str(k): v for k, v in body.weekday_adj.items()}
    values.update(tenant_id=tenant_id, hotel_id=hid, updated_by=principal.user_id)
    await session.execute(
        insert(PriceStrategy)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[PriceStrategy.tenant_id, PriceStrategy.hotel_id],
            set_={k: v for k, v in values.items() if k not in ("tenant_id", "hotel_id")},
        )
    )
    await session.commit()
    return _strategy_out(
        hid, await session.get(PriceStrategy, (tenant_id, hid), populate_existing=True)
    )


async def _actuals(
    session: SessionDep, tenant_id: int, hid: int, start: date, end: date
) -> dict[date, tuple[Decimal, Decimal | None]]:
    """Công suất (0..1) và ADR thật của các đêm đã qua: PMS; thiếu PMS thì OTB lúc đến."""
    out: dict[date, tuple[Decimal, Decimal | None]] = {}
    for d, occ, adr, sold, total, avail in await session.execute(
        select(
            OwnHotelDaily.stay_date,
            OwnHotelDaily.occupancy_pct,
            OwnHotelDaily.adr,
            OwnHotelDaily.rooms_sold,
            OwnHotelDaily.rooms_total,
            OwnHotelDaily.rooms_available,
        ).where(
            OwnHotelDaily.tenant_id == tenant_id,
            OwnHotelDaily.hotel_id == hid,
            OwnHotelDaily.stay_date >= start,
            OwnHotelDaily.stay_date <= end,
        )
    ):
        cap = total or ((sold or 0) + avail if avail is not None else None)
        value = (
            Decimal(occ) / 100
            if occ is not None
            else (Decimal(sold) / cap if sold is not None and cap else None)
        )
        if value is not None:
            out[d] = (value.quantize(Decimal("0.0001")), adr)
    for d, rooms, cap, rev in await session.execute(
        select(
            OtbSnapshot.stay_date,
            OtbSnapshot.rooms_otb,
            OtbSnapshot.rooms_available,
            OtbSnapshot.revenue_otb,
        ).where(
            OtbSnapshot.tenant_id == tenant_id,
            OtbSnapshot.hotel_id == hid,
            OtbSnapshot.stay_date >= start,
            OtbSnapshot.stay_date <= end,
            OtbSnapshot.as_of_date == OtbSnapshot.stay_date,
        )
    ):
        if d not in out and cap:
            out[d] = (
                (Decimal(rooms) / cap).quantize(Decimal("0.0001")),
                (rev / rooms).quantize(Decimal("0.01")) if rev is not None and rooms else None,
            )
    return out


@router.get("/suggestions/outcomes", response_model=OutcomesOut)
async def suggestion_outcomes(
    tenant_id: TenantDep,
    session: SessionDep,
    days: int = Query(60, ge=7, le=365),
    own_hotel_id: int | None = None,
) -> OutcomesOut:
    """Gợi ý đã áp dụng/bỏ qua → kết quả sau đêm lưu trú (công suất, ADR thật)."""
    tenant = await _tenant(session, tenant_id)
    today = tenant_today(tenant)
    hid = await _own_hotel(session, tenant_id, own_hotel_id)
    rows = list(
        (
            await session.execute(
                select(PriceSuggestionDecision)
                .where(
                    PriceSuggestionDecision.tenant_id == tenant_id,
                    PriceSuggestionDecision.stay_date >= today - timedelta(days=days),
                )
                .order_by(PriceSuggestionDecision.stay_date)
            )
        ).scalars()
    )
    actual = await _actuals(session, tenant_id, hid, today - timedelta(days=days), today)
    nights = []
    for r in rows:
        occ_adr = actual.get(r.stay_date) if r.stay_date < today else None
        verdict = (
            "pending"
            if occ_adr is None
            else backtest_verdict(r.kind, occ_adr[0])
            if r.decision == "applied"
            else "neutral"
        )
        nights.append(
            OutcomeNightOut(
                stay_date=r.stay_date,
                kind=r.kind,
                decision=r.decision,
                change_pct=r.change_pct,
                own_price=r.own_price,
                target_price=r.target_price,
                applied_price=r.applied_price,
                actual_occ_pct=(occ_adr[0] * 100).quantize(Decimal("0.1")) if occ_adr else None,
                actual_adr=occ_adr[1] if occ_adr else None,
                verdict=verdict,
            )
        )
    applied = sum(1 for r in rows if r.decision == "applied")
    return OutcomesOut(
        decided=len(rows),
        applied=applied,
        dismissed=len(rows) - applied,
        apply_rate=(Decimal(applied) / len(rows)).quantize(Decimal("0.01")) if rows else None,
        good=sum(1 for n in nights if n.verdict == "good"),
        review=sum(1 for n in nights if n.verdict == "review"),
        nights=nights,
    )


@router.get("/suggestions/backtest", response_model=BacktestOut)
async def suggestion_backtest(
    tenant_id: TenantDep,
    session: SessionDep,
    days: int = Query(60, ge=7, le=180),
    lead: int = Query(7, ge=1, le=30),
    own_hotel_id: int | None = None,
) -> BacktestOut:
    """Backtest (6.4): với mỗi đêm đã qua có công suất thật, chạy lại luật gợi ý trên quan sát giá
    và tình trạng phòng của compset khoảng `lead` ngày trước đêm đó, rồi chấm hướng gợi ý."""
    tenant = await _tenant(session, tenant_id)
    today = tenant_today(tenant)
    hid = await _own_hotel(session, tenant_id, own_hotel_id)
    w = await load_compset(session, tenant_id, hid)
    start = today - timedelta(days=days)
    actual = await _actuals(session, tenant_id, hid, start, today - timedelta(days=1))
    channel = tenant_channel()
    strat_row = await session.get(PriceStrategy, (tenant_id, hid))
    strategy = strategy_from(strat_row)
    if strat_row is None:
        typical = await typical_index(session, hid, w.competitors, channel, today)
        if typical is not None:
            strategy = replace(strategy, target_index=typical, target_source="typical")
    ids = [hid, *w.competitors]
    snaps: dict[tuple[int, date], list[HotelDateSnapshot]] = {}
    if actual:
        for row in (
            await session.execute(
                select(HotelDateSnapshot).where(
                    HotelDateSnapshot.hotel_id.in_(ids),
                    HotelDateSnapshot.channel == channel,
                    HotelDateSnapshot.stay_date.in_(list(actual)),
                )
            )
        ).scalars():
            snaps.setdefault((row.hotel_id, row.stay_date), []).append(row)

    def at_lead(hotel: int, d: date) -> HotelDateSnapshot | None:
        cands = [
            r
            for r in snaps.get((hotel, d), [])
            if lead - 1 <= (d - r.scanned_at.date()).days <= lead + 1
        ]
        return max(cands, key=lambda r: r.scanned_at) if cands else None

    details = []
    for d, (occ, adr) in sorted(actual.items()):
        own = at_lead(hid, d)
        comps = [x for c in w.competitors if (x := at_lead(c, d)) is not None]
        if own is None or own.status != "available" or own.min_price is None:
            continue
        prices = [
            c.min_price
            for c in comps
            if c.status == "available" and c.min_price is not None and (c.min_stay or 1) == 1
        ]
        sig = NightSignals(
            stay_date=d,
            days_to_arrival=lead,
            own_status="available",
            own_price=own.min_price,
            own_rooms_left=own.exact_rooms_left,
            own_occ=None,
            comp_observed=sum(1 for c in comps if c.status in ("available", "sold_out")),
            comp_sold_out=sum(1 for c in comps if c.status == "sold_out"),
            comp_median_price=median(prices) if len(prices) >= 3 else None,
            comp_occ=None,
            comp_pace=None,
            comp_priced=len(prices),
            comp_low=sum(
                1
                for c in comps
                if c.status == "available"
                and c.exact_rooms_left is not None
                and c.exact_rooms_left <= 3
            ),
        )
        sug = suggest(sig, strategy)
        if sug is None:
            continue
        details.append(
            OutcomeNightOut(
                stay_date=d,
                kind=sug.kind,
                decision="backtest",
                change_pct=sug.change_pct,
                own_price=own.min_price,
                target_price=sug.target_price,
                applied_price=None,
                actual_occ_pct=(occ * 100).quantize(Decimal("0.1")),
                actual_adr=adr,
                verdict=backtest_verdict(sug.kind, occ),
            )
        )
    scored = [x for x in details if x.verdict in ("good", "review")]
    good = sum(1 for x in scored if x.verdict == "good")
    return BacktestOut(
        nights=len(details),
        raise_nights=sum(1 for x in details if x.kind == "raise"),
        lower_nights=sum(1 for x in details if x.kind == "lower"),
        good=good,
        review=len(scored) - good,
        hit_rate=(Decimal(good) / len(scored)).quantize(Decimal("0.01")) if scored else None,
        details=details,
    )
