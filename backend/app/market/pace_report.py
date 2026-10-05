"""Báo cáo nhịp đặt phòng của tenant theo từng đêm: công suất ước tính (của bạn và thị trường),
nhịp so cùng kỳ, đối chiếu PMS, gợi ý giá. Đọc trên kênh tham chiếu của tenant (mặc định Booking),
nơi số phòng còn được lộ rõ nhất.

Tenant chuỗi có nhiều khách sạn `self`: mỗi khách sạn một gợi ý riêng (`NightReport.suggestions`,
theo thứ tự hotel_id); các cột `own_*` và `suggestion` của đêm là của khách sạn chính (id nhỏ
nhất) để giữ tương thích."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.rules import median
from app.db.models import HotelDateMetric, OwnHotelDaily, Tenant, TenantHotel
from app.holidays.data import holidays_between
from app.i18n import DEFAULT_LOCALE
from app.market.models import OccupancyEstimate, PriceSuggestionDecision
from app.market.occupancy import Q4, is_reliable
from app.market.pacing import (
    LEAD_TOLERANCE,
    REFERENCE_WEEKS,
    Calibration,
    Pace,
    calibrate,
    compset_curve,
    pace,
)
from app.market.price_suggest import (
    DEFAULT_THRESHOLDS,
    NightSignals,
    PriceQuote,
    Suggestion,
    SuggestionThresholds,
    comparable,
    price_basis,
    suggest,
)

HISTORY = timedelta(weeks=max(REFERENCE_WEEKS))  # đêm tham chiếu xa nhất: 8 tuần trước
CALIBRATION_DAYS = 60
# Đêm mà lần quét mới nhất cũ hơn STALE_DAYS ngày: không nạp quan sát cũ hơn nữa (không coi ước
# tính cả tuần trước là "hiện tại"). PICKUP_LEAD: `_pickup_7d` nhìn lại tối đa 8 mốc lead.
STALE_DAYS = 7
PICKUP_LEAD = 8


@dataclass(frozen=True)
class Obs:
    stay_date: date
    lead: int
    scanned_at: datetime
    status: str
    inventory: int
    left_low: int
    left_high: int
    occ_low: Decimal
    occ_high: Decimal
    coverage: Decimal

    @property
    def left_mid(self) -> Decimal:
        return Decimal(self.left_low + self.left_high) / 2

    @property
    def occ_mid(self) -> Decimal:
        return ((self.occ_low + self.occ_high) / 2).quantize(Q4)

    @property
    def reliable(self) -> bool:
        return is_reliable(self.coverage, self.occ_low, self.occ_high)


@dataclass(frozen=True)
class OwnSuggestion:
    """Gợi ý của một khách sạn `self` cho một đêm, kèm ghi nhận còn hiệu lực (nếu có)."""

    hotel_id: int
    suggestion: Suggestion
    decision: str | None
    own_price: Decimal | None  # giá của khách sạn đó theo cơ sở gợi ý (ghi vào quyết định)
    currency: str | None


@dataclass
class NightReport:
    stay_date: date
    days_to_arrival: int
    holiday: str | None
    own_obs: Obs | None
    own_pms_occ: Decimal | None
    own_pace: Pace
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
    comp_pace: Pace
    suggestion: Suggestion | None  # của khách sạn self chính (id nhỏ nhất)
    decision: str | None
    suggestions: list[OwnSuggestion] = field(default_factory=list)  # mọi khách sạn self


@dataclass
class PaceReport:
    start: date
    end: date
    channel: str
    own_hotel_id: int | None
    nights: list[NightReport] = field(default_factory=list)
    calibration: Calibration = field(default_factory=lambda: Calibration(0, None, None))
    data_since: date | None = None


def tenant_today(tenant: Tenant, now: datetime | None = None) -> date:
    try:
        tz = ZoneInfo(tenant.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return (now or datetime.now(tz=UTC)).astimezone(tz).date()


async def _observations(
    s: AsyncSession,
    hotel_ids: list[int],
    channel: str,
    start: date,
    end: date,
    today: date,
    calibrate_hotel: int | None,
) -> dict[int, dict[date, list[Obs]]]:
    """Mỗi (khách sạn, đêm, số ngày trước khi đến) giữ lần quét mới nhất. Chỉ nạp cửa sổ lead cần:
    - đêm hiển thị [start, end]: quan sát trong STALE_DAYS + PICKUP_LEAD + dung sai ngày trước mốc
      hiện tại của đêm (mốc = hôm nay, hoặc chính đêm đó nếu đã qua);
    - đêm tham chiếu (cùng thứ, 1–8 tuần trước đêm hiển thị): quan sát ở cùng lead với đêm hiển
      thị (± dung sai, + STALE_DAYS khi lần quét mới nhất đã cũ);
    - đêm hiệu chuẩn (khách sạn bạn, CALIBRATION_DAYS ngày qua): lead ≤ LEAD_TOLERANCE + 1."""
    night, lead = OccupancyEstimate.stay_date, OccupancyEstimate.days_to_arrival
    display_window = STALE_DAYS + PICKUP_LEAD + LEAD_TOLERANCE
    needed = [
        and_(
            night >= start,
            night <= end,
            lead <= func.greatest(night - today, 0) + display_window,
        ),
        and_(
            night >= start - HISTORY,
            night <= end - timedelta(weeks=min(REFERENCE_WEEKS)),
            lead >= (start - today).days - LEAD_TOLERANCE,
            lead <= (end - today).days + STALE_DAYS + LEAD_TOLERANCE,
        ),
    ]
    if calibrate_hotel is not None:
        needed.append(
            and_(
                OccupancyEstimate.hotel_id == calibrate_hotel,
                night >= today - timedelta(days=CALIBRATION_DAYS),
                night < today,
                lead <= LEAD_TOLERANCE + 1,
            )
        )
    q = (
        select(
            OccupancyEstimate.hotel_id,
            OccupancyEstimate.stay_date,
            OccupancyEstimate.days_to_arrival,
            OccupancyEstimate.scanned_at,
            OccupancyEstimate.status,
            OccupancyEstimate.inventory,
            OccupancyEstimate.left_low,
            OccupancyEstimate.left_high,
            OccupancyEstimate.occ_low,
            OccupancyEstimate.occ_high,
            OccupancyEstimate.coverage,
        )
        .where(
            OccupancyEstimate.hotel_id.in_(hotel_ids),
            OccupancyEstimate.channel == channel,
            or_(*needed),
        )
        .distinct(
            OccupancyEstimate.hotel_id,
            OccupancyEstimate.stay_date,
            OccupancyEstimate.days_to_arrival,
        )
        .order_by(
            OccupancyEstimate.hotel_id,
            OccupancyEstimate.stay_date,
            OccupancyEstimate.days_to_arrival,
            OccupancyEstimate.scanned_at.desc(),
        )
    )
    out: dict[int, dict[date, list[Obs]]] = defaultdict(lambda: defaultdict(list))
    for hid, d, lead_, at, status, inv, llo, lhi, lo, hi, cov in (await s.execute(q)).all():
        out[hid][d].append(Obs(d, lead_, at, status, inv, llo, lhi, lo, hi, cov))
    return out


def _latest(obs: list[Obs]) -> Obs | None:
    return max(obs, key=lambda o: o.scanned_at) if obs else None


async def latest_observations(
    s: AsyncSession, hotel_ids: list[int], channel: str, start: date, end: date
) -> dict[int, dict[date, Obs]]:
    """Ước tính mới nhất của mỗi (khách sạn, đêm) trên một kênh (công suất từng khách sạn)."""
    if not hotel_ids:
        return {}
    q = (
        select(
            OccupancyEstimate.hotel_id,
            OccupancyEstimate.stay_date,
            OccupancyEstimate.days_to_arrival,
            OccupancyEstimate.scanned_at,
            OccupancyEstimate.status,
            OccupancyEstimate.inventory,
            OccupancyEstimate.left_low,
            OccupancyEstimate.left_high,
            OccupancyEstimate.occ_low,
            OccupancyEstimate.occ_high,
            OccupancyEstimate.coverage,
        )
        .where(
            OccupancyEstimate.hotel_id.in_(hotel_ids),
            OccupancyEstimate.channel == channel,
            OccupancyEstimate.stay_date >= start,
            OccupancyEstimate.stay_date <= end,
        )
        # Chỉ lần quét mới nhất của mỗi (khách sạn, đêm): không kéo mọi mốc lead time về Python.
        .distinct(OccupancyEstimate.hotel_id, OccupancyEstimate.stay_date)
        .order_by(
            OccupancyEstimate.hotel_id,
            OccupancyEstimate.stay_date,
            OccupancyEstimate.scanned_at.desc(),
        )
    )
    out: dict[int, dict[date, Obs]] = defaultdict(dict)
    for hid, d, lead, at, st, inv, llo, lhi, lo, hi, cov in (await s.execute(q)).all():
        out[hid][d] = Obs(d, lead, at, st, inv, llo, lhi, lo, hi, cov)
    return out


def _curve(obs: list[Obs]) -> dict[int, Decimal]:
    return {o.lead: o.occ_mid for o in obs if o.reliable}


def _pickup_7d(obs: list[Obs]) -> int | None:
    """Phòng bán thêm trong 7 ngày qua = phòng còn 7 ngày trước − phòng còn bây giờ (giữa khoảng).
    Lấy hiệu số phòng còn, không qua công suất, để không lệch khi inventory ước tính thay đổi.
    Âm = đối thủ mở thêm phòng hoặc có huỷ."""
    now = _latest(obs)
    if now is None or not now.reliable:
        return None
    by_lead = {o.lead: o for o in obs if o.reliable}
    then = next(
        (by_lead[d] for d in (now.lead + 7, now.lead + 8, now.lead + 6) if d in by_lead), None
    )
    if then is None:
        return None
    return int((then.left_mid - now.left_mid).quantize(Decimal(1)))


def _decision(stored: tuple[str, int] | None, sug: Suggestion | None) -> str | None:
    if stored is None or sug is None or stored[1] != sug.change_pct:
        return None
    return stored[0]


def _quote(m: HotelDateMetric) -> PriceQuote:
    return PriceQuote(m.currency, m.min_price, m.min_refundable_price)


@dataclass(frozen=True)
class _OwnNight:
    """Tín hiệu một đêm nhìn từ một khách sạn `self` (đối thủ đã lọc tiền tệ theo khách sạn đó)."""

    obs: Obs | None
    signals: NightSignals
    currency: str | None
    suggestion: Suggestion | None


def _own_night(
    d: date,
    today: date,
    obs: list[Obs],
    pms_occ: Decimal | None,
    own_m: HotelDateMetric | None,
    comp_all: list[HotelDateMetric],
    comp_occ: Decimal | None,
    comp_pace: Decimal | None,
    holiday: str | None,
    thresholds: SuggestionThresholds,
) -> _OwnNight:
    own_obs = _latest(obs)
    own_occ_now = own_obs.occ_mid if own_obs and own_obs.reliable else None
    own_q = _quote(own_m) if own_m else None
    own_currency = own_q.currency if own_q else None
    comp_m = [m for m in comp_all if comparable(own_currency, _quote(m))]
    pick = price_basis(own_q, [_quote(m) for m in comp_m])
    signals = NightSignals(
        stay_date=d,
        days_to_arrival=(d - today).days,
        own_status=own_m.availability_status if own_m else None,
        own_price=pick.own_price,
        own_rooms_left=own_m.exact_rooms_left if own_m else None,
        own_occ=pms_occ if pms_occ is not None else own_occ_now,
        comp_observed=len(comp_m),
        comp_sold_out=sum(1 for m in comp_m if m.availability_status == "sold_out"),
        comp_median_price=median(pick.comp_prices),
        comp_occ=comp_occ,
        comp_pace=comp_pace,
        holiday=holiday,
        price_basis=pick.basis,
    )
    sug = suggest(signals, thresholds) if d >= today else None
    currency = own_currency or next((m.currency for m in comp_m if m.currency), None)
    return _OwnNight(own_obs, signals, currency, sug)


async def build_pace_report(
    s: AsyncSession,
    tenant_id: int,
    start: date,
    end: date,
    today: date | None = None,
    locale: str = DEFAULT_LOCALE,
    thresholds: SuggestionThresholds = DEFAULT_THRESHOLDS,
) -> PaceReport:
    """`locale`: ngôn ngữ tên ngày lễ (cũng là tham số của lý do gợi ý giá)."""
    tenant = await s.get(Tenant, tenant_id)
    if tenant is None:
        raise LookupError("tenant not found")
    today = today or tenant_today(tenant)
    channel = tenant.reference_channel or "booking"
    links = (
        await s.execute(
            select(TenantHotel.hotel_id, TenantHotel.role)
            .where(TenantHotel.tenant_id == tenant_id, TenantHotel.active.is_(True))
            .order_by(TenantHotel.hotel_id)
        )
    ).all()
    own_ids = [h for h, r in links if r == "self"]
    comp_ids = [h for h, r in links if r == "competitor"]
    own_id = own_ids[0] if own_ids else None  # khách sạn chính: id nhỏ nhất, ổn định giữa request
    report = PaceReport(start, end, channel, own_id)
    ids = own_ids + comp_ids
    if not ids:
        return report

    obs = await _observations(s, ids, channel, start, end, today, own_id)
    holidays = {
        h.date: h.name for h in holidays_between(tenant.country_code, start - HISTORY, end, locale)
    }

    def is_holiday(d: date) -> bool:
        return d in holidays

    own_curves = {d: _curve(o) for d, o in obs.get(own_id, {}).items()} if own_id else {}
    # Chỉ các đêm hiển thị và đêm tham chiếu của chúng (cùng thứ, 1–8 tuần trước).
    nights_needed = {
        d - timedelta(weeks=w)
        for i in range((end - start).days + 1)
        for d in [start + timedelta(days=i)]
        for w in (0, *REFERENCE_WEEKS)
    }
    comp_curves = {
        d: compset_curve(_curve(obs[c][d]) for c in comp_ids if d in obs.get(c, {}))
        for d in nights_needed
    }

    metrics = {
        (m.hotel_id, m.stay_date): m
        for m in (
            await s.execute(
                select(HotelDateMetric).where(
                    HotelDateMetric.hotel_id.in_(ids),
                    HotelDateMetric.channel == channel,
                    HotelDateMetric.stay_date >= start,
                    HotelDateMetric.stay_date <= end,
                )
            )
        ).scalars()
    }
    pms: dict[int, dict[date, Decimal]] = defaultdict(dict)
    decisions: dict[tuple[int, date, str], tuple[str, int]] = {}
    if own_ids:
        for hid, d, pct in await s.execute(
            select(
                OwnHotelDaily.hotel_id, OwnHotelDaily.stay_date, OwnHotelDaily.occupancy_pct
            ).where(
                OwnHotelDaily.tenant_id == tenant_id,
                OwnHotelDaily.hotel_id.in_(own_ids),
                OwnHotelDaily.stay_date >= min(start, today - timedelta(days=CALIBRATION_DAYS)),
                OwnHotelDaily.stay_date <= end,
            )
        ):
            if pct is not None:
                pms[hid][d] = (Decimal(pct) / 100).quantize(Q4)
        decisions = {
            (hid, d, k): (dec, pct)
            for hid, d, k, dec, pct in await s.execute(
                select(
                    PriceSuggestionDecision.hotel_id,
                    PriceSuggestionDecision.stay_date,
                    PriceSuggestionDecision.kind,
                    PriceSuggestionDecision.decision,
                    PriceSuggestionDecision.change_pct,
                ).where(
                    PriceSuggestionDecision.tenant_id == tenant_id,
                    PriceSuggestionDecision.hotel_id.in_(own_ids),
                    PriceSuggestionDecision.stay_date >= start,
                    PriceSuggestionDecision.stay_date <= end,
                )
            )
        }

    d = start
    while d <= end:
        comp_latest = [o for c in comp_ids if (o := _latest(obs.get(c, {}).get(d, [])))]
        reliable = [o.occ_mid for o in comp_latest if o.reliable]
        comp_med = median(reliable) if len(reliable) >= 2 else None
        comp_occ = comp_med.quantize(Q4) if comp_med is not None else None
        comp_curve_now = comp_curves.get(d, {})
        comp_pace = Pace(None, 0, None)
        if comp_curve_now:
            lead = min(comp_curve_now)
            comp_pace = pace(d, lead, comp_curve_now[lead], comp_curves, is_holiday)
        pickups = [p for c in comp_ids if (p := _pickup_7d(obs.get(c, {}).get(d, []))) is not None]
        comp_all = [
            m for c in comp_ids if (m := metrics.get((c, d))) and m.availability_status != "unknown"
        ]

        # Mỗi khách sạn self một bộ tín hiệu (giá, tiền tệ, PMS riêng); đối thủ dùng chung.
        per_own: dict[int | None, _OwnNight] = {}
        for hid in own_ids or [None]:
            per_own[hid] = _own_night(
                d,
                today,
                obs.get(hid, {}).get(d, []) if hid else [],
                pms[hid].get(d) if hid else None,
                metrics.get((hid, d)) if hid else None,
                comp_all,
                comp_occ,
                comp_pace.delta,
                holidays.get(d),
                thresholds,
            )
        primary = per_own[own_id]
        own_obs, signals = primary.obs, primary.signals
        own_occ_now = own_obs.occ_mid if own_obs and own_obs.reliable else None
        own_pace = (
            pace(d, own_obs.lead, own_occ_now, own_curves, is_holiday)
            if own_obs
            else Pace(None, 0, None)
        )
        suggestions = [
            # Ghi nhận chỉ còn hiệu lực khi gợi ý giữ nguyên mức (đổi mức thì hỏi lại).
            OwnSuggestion(
                hid,
                sug,
                _decision(decisions.get((hid, d, sug.kind)), sug),
                o.signals.own_price,
                o.currency,
            )
            for hid, o in per_own.items()
            if hid is not None and (sug := o.suggestion) is not None
        ]
        report.nights.append(
            NightReport(
                stay_date=d,
                days_to_arrival=(d - today).days,
                holiday=holidays.get(d),
                own_obs=own_obs,
                own_pms_occ=pms[own_id].get(d) if own_id else None,
                own_pace=own_pace,
                own_price=signals.own_price,
                own_status=signals.own_status,
                own_rooms_left=signals.own_rooms_left,
                currency=primary.currency,
                comp_observed=signals.comp_observed,
                comp_sold_out=signals.comp_sold_out,
                comp_median_price=signals.comp_median_price,
                comp_occ=comp_occ,
                comp_occ_hotels=len(reliable),
                comp_pickup_7d=sum(pickups) if pickups else None,
                comp_pickup_hotels=len(pickups),
                comp_pace=comp_pace,
                suggestion=primary.suggestion,
                decision=next((o.decision for o in suggestions if o.hotel_id == own_id), None),
                suggestions=suggestions,
            )
        )
        d += timedelta(days=1)

    if own_id:
        pairs = []
        for night, real in pms[own_id].items():
            if not today - timedelta(days=CALIBRATION_DAYS) <= night < today:
                continue
            last = _latest([o for o in obs.get(own_id, {}).get(night, []) if o.reliable])
            if last is not None and last.lead <= LEAD_TOLERANCE + 1:
                pairs.append((last.occ_mid, real))
        report.calibration = calibrate(pairs)
    first = (
        await s.execute(
            select(func.min(OccupancyEstimate.scanned_at)).where(
                OccupancyEstimate.hotel_id.in_(ids), OccupancyEstimate.channel == channel
            )
        )
    ).scalar_one()
    report.data_since = first.date() if first else None
    return report
