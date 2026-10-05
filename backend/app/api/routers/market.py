"""Nhịp đặt phòng và gợi ý giá (đợt 2). Schema nằm trong file này để module tự đứng riêng."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import LocaleDep, SessionDep, SettingsDep, TenantDep, WriterDep
from app.api.schemas import HolidayOut
from app.db.models import Hotel, Tenant, TenantHotel
from app.holidays.data import holidays_between
from app.i18n import t
from app.logging import get_logger
from app.market.models import LocalEvent, PriceSuggestionDecision
from app.market.pace_report import (
    NightReport,
    PaceReport,
    build_pace_report,
    latest_observations,
    tenant_today,
)
from app.market.pacing import Pace
from app.market.price_suggest import Suggestion, reason_text
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


class SuggestionOut(BaseModel):
    kind: Literal["raise", "hold", "lower"]
    change_pct: int
    confidence: Literal["high", "medium"]
    reasons: list[str]
    decision: Literal["applied", "dismissed"] | None


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
    comp_pickup_7d: int | None
    comp_pickup_hotels: int
    comp_pace: PaceOut
    suggestion: SuggestionOut | None


class CalibrationOut(BaseModel):
    nights: int
    mean_abs_error_pts: Decimal | None
    bias_pts: Decimal | None


class MarketPaceOut(BaseModel):
    start: date
    end: date
    channel: str
    own_hotel_id: int | None
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


def _pace(p: Pace) -> PaceOut:
    return PaceOut(reference=p.reference, references=p.references, delta=p.delta)


def _suggestion(s: Suggestion, decision: str | None, locale: str) -> SuggestionOut:
    return SuggestionOut(
        kind=s.kind,
        change_pct=s.change_pct,
        confidence=s.confidence,
        reasons=[reason_text(r, locale) for r in s.reasons],
        decision=decision,
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
        data_since=r.data_since,
        calibration=CalibrationOut(
            nights=r.calibration.nights,
            mean_abs_error_pts=r.calibration.mean_abs_error_pts,
            bias_pts=r.calibration.bias_pts,
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
) -> MarketPaceOut:
    tenant = await _tenant(session, tenant_id)
    today = tenant_today(tenant)
    s = start or today
    e = end or s + timedelta(days=DEFAULT_DAYS - 1)
    if abs((s - today).days) > 730 or e < s or (e - s).days >= MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"range must be 1–{MAX_RANGE_DAYS} nights"
        )
    return _out(await build_pace_report(session, tenant_id, s, e, today, locale), locale)


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
        for h in holidays_between(tenant.country_code, s, e, locale)
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
    """Công suất ước tính mới nhất của từng khách sạn trong watchlist theo đêm (kênh tham chiếu)."""
    tenant = await _tenant(session, tenant_id)
    s = start or tenant_today(tenant)
    e = end or s + timedelta(days=DEFAULT_DAYS - 1)
    if e < s or (e - s).days >= MAX_RANGE_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"range must be 1–{MAX_RANGE_DAYS} nights"
        )
    channel = tenant.reference_channel or "booking"
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
        category=e.category,  # type: ignore[arg-type]
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
