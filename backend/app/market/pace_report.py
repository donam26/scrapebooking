"""Báo cáo nhịp đặt phòng của tenant theo từng đêm: chỉ báo lấp đầy ước tính (của bạn và đối
thủ), nhịp so các tuần trước cùng thứ, đối chiếu PMS, gợi ý giá. Đọc trên một kênh (mặc định kênh
tham chiếu của tenant, nơi số phòng còn được lộ rõ nhất)."""

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.compset import load_compset
from app.analytics.rules import median
from app.channels.registry import BOOKING
from app.db.models import HotelDateMetric, OwnHotelDaily, Tenant
from app.holidays.data import holidays_between
from app.i18n import DEFAULT_LOCALE
from app.market.models import (
    LocalEvent,
    OccupancyEstimate,
    OtbSnapshot,
    PriceStrategy,
    PriceSuggestionDecision,
)
from app.market.occupancy import Q4, is_reliable
from app.market.pacing import (
    LEAD_BUCKETS,
    LEAD_TOLERANCE,
    REFERENCE_WEEKS,
    Calibration,
    LeadCalibration,
    Pace,
    calibrate,
    calibrate_by_lead,
    compset_curve,
    pace,
)
from app.market.price_suggest import NightSignals, Strategy, Suggestion, suggest

HISTORY = timedelta(weeks=max(REFERENCE_WEEKS) + 1)
CALIBRATION_DAYS = 60


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
    comp_occ_low: Decimal | None
    comp_occ_high: Decimal | None
    comp_priced: int
    comp_pickup_7d: int | None
    comp_pickup_hotels: int
    comp_pace: Pace
    suggestion: Suggestion | None
    decision: str | None


@dataclass
class PaceReport:
    start: date
    end: date
    channel: str
    own_hotel_id: int | None
    nights: list[NightReport] = field(default_factory=list)
    calibration: Calibration = field(default_factory=lambda: Calibration(0, None, None))
    calibration_by_lead: list[LeadCalibration] = field(default_factory=list)
    data_since: date | None = None
    own_hotel_ids: list[int] = field(default_factory=list)


def strategy_from(row: PriceStrategy | None) -> Strategy:
    if row is None:
        return Strategy()
    return Strategy(
        target_source="strategy",
        base_price=row.base_price,
        floor=row.floor_price,
        ceiling=row.ceiling_price,
        target_index=Decimal(row.target_index),
        round_to=row.round_to,
        max_daily_change_pct=row.max_daily_change_pct,
        weekday_adj={int(k): int(v) for k, v in (row.weekday_adj or {}).items()},
        holiday_uplift_pct=row.holiday_uplift_pct,
        last_minute_days=row.last_minute_days,
        last_minute_adj_pct=row.last_minute_adj_pct,
    )


async def load_strategy(s: AsyncSession, tenant_id: int, hotel_id: int) -> Strategy:
    return strategy_from(await s.get(PriceStrategy, (tenant_id, hotel_id)))


TYPICAL_WINDOW = 30


async def typical_index(
    s: AsyncSession, own_id: int, comp_ids: list[int], channel: str, today: date
) -> Decimal | None:
    """Định vị thường ngày của khách sạn: trung vị chỉ số giá niêm yết (giá bạn / trung vị đối
    thủ × 100) trên các đêm 30 ngày tới có ≥3 đối thủ có giá 1 đêm. Cố định theo ngày, không theo
    khoảng đang xem, để màn hình và lúc ghi quyết định ra cùng một gợi ý."""
    rows = await s.execute(
        select(
            HotelDateMetric.hotel_id,
            HotelDateMetric.stay_date,
            HotelDateMetric.min_price,
        ).where(
            HotelDateMetric.hotel_id.in_([own_id, *comp_ids]),
            HotelDateMetric.channel == channel,
            HotelDateMetric.stay_date >= today,
            HotelDateMetric.stay_date < today + timedelta(days=TYPICAL_WINDOW),
            HotelDateMetric.availability_status == "available",
            HotelDateMetric.min_stay == 1,
            HotelDateMetric.min_price.is_not(None),
        )
    )
    own: dict[date, Decimal] = {}
    comp: dict[date, list[Decimal]] = defaultdict(list)
    for hid, d, price in rows:
        if hid == own_id:
            own[d] = price
        else:
            comp[d].append(price)
    idx = []
    for d, price in own.items():
        prices = comp.get(d, [])
        med = median(prices) if len(prices) >= 3 else None
        if med:
            idx.append(price / med * 100)
    m = median(idx)
    if m is None:
        return None
    return max(Decimal(50), min(Decimal(200), m.quantize(Decimal(1))))


def tenant_today(tenant: Tenant, now: datetime | None = None) -> date:
    try:
        tz = ZoneInfo(tenant.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return (now or datetime.now(tz=UTC)).astimezone(tz).date()


async def _observations(
    s: AsyncSession, hotel_ids: list[int], channel: str, start: date, end: date
) -> dict[int, dict[date, list[Obs]]]:
    """Mỗi (khách sạn, đêm, số ngày trước khi đến) giữ lần quét mới nhất."""
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
    for hid, d, lead, at, status, inv, llo, lhi, lo, hi, cov in (await s.execute(q)).all():
        out[hid][d].append(Obs(d, lead, at, status, inv, llo, lhi, lo, hi, cov))
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


async def build_pace_report(
    s: AsyncSession,
    tenant_id: int,
    start: date,
    end: date,
    today: date | None = None,
    locale: str = DEFAULT_LOCALE,
    own_hotel_id: int | None = None,
) -> PaceReport:
    """`locale`: ngôn ngữ tên ngày lễ (cũng là tham số của lý do gợi ý giá). `own_hotel_id`:
    khách sạn của bạn đang xem (5.5); mặc định khách sạn đầu tiên. Dữ liệu Booking.com."""
    tenant = await s.get(Tenant, tenant_id)
    if tenant is None:
        raise LookupError("tenant not found")
    today = today or tenant_today(tenant)
    channel = BOOKING
    w = await load_compset(s, tenant_id, own_hotel_id)
    own_id = own_hotel_id if own_hotel_id in w.own else (w.own[0] if w.own else None)
    own_ids = [own_id] if own_id else []
    comp_ids = w.competitors
    report = PaceReport(start, end, channel, own_id, own_hotel_ids=w.own)
    ids = own_ids + comp_ids
    if not ids:
        return report

    hist_start = min(start, today - timedelta(days=CALIBRATION_DAYS)) - HISTORY
    obs = await _observations(s, ids, channel, hist_start, end)
    holidays = {
        h.date: h.name for h in holidays_between(tenant.country_code, hist_start, end, locale)
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
    pms: dict[date, Decimal] = {}
    if own_id:
        for d, pct in await s.execute(
            select(OwnHotelDaily.stay_date, OwnHotelDaily.occupancy_pct).where(
                OwnHotelDaily.tenant_id == tenant_id,
                OwnHotelDaily.hotel_id == own_id,
                OwnHotelDaily.stay_date >= hist_start,
                OwnHotelDaily.stay_date <= end,
            )
        ):
            if pct is not None:
                pms[d] = (Decimal(pct) / 100).quantize(Q4)
    decisions = {
        (d, k): (dec, pct)
        for d, k, dec, pct in await s.execute(
            select(
                PriceSuggestionDecision.stay_date,
                PriceSuggestionDecision.kind,
                PriceSuggestionDecision.decision,
                PriceSuggestionDecision.change_pct,
            ).where(
                PriceSuggestionDecision.tenant_id == tenant_id,
                PriceSuggestionDecision.stay_date >= start,
                PriceSuggestionDecision.stay_date <= end,
            )
        )
    }

    strategy = Strategy()
    if own_id:
        row = await s.get(PriceStrategy, (tenant_id, own_id))
        strategy = strategy_from(row)
        if row is None:
            typical = await typical_index(s, own_id, comp_ids, channel, today)
            if typical is not None:
                strategy = replace(strategy, target_index=typical, target_source="typical")
    otb_curves: dict[date, dict[int, int]] = {}
    otb_latest: dict[date, tuple[int, int | None]] = {}  # đêm -> (phòng OTB, sức chứa)
    if own_id:
        for as_of, stay, rooms, cap in await s.execute(
            select(
                OtbSnapshot.as_of_date,
                OtbSnapshot.stay_date,
                OtbSnapshot.rooms_otb,
                OtbSnapshot.rooms_available,
            ).where(
                OtbSnapshot.tenant_id == tenant_id,
                OtbSnapshot.hotel_id == own_id,
                OtbSnapshot.stay_date >= start - timedelta(weeks=5),
                OtbSnapshot.stay_date <= end,
                OtbSnapshot.as_of_date <= today,
            )
        ):
            otb_curves.setdefault(stay, {})[(stay - as_of).days] = rooms
            prev = otb_latest.get(stay)
            if prev is None or (stay - as_of).days <= min(otb_curves[stay]):
                otb_latest[stay] = (rooms, cap)
    events = [
        (ev.start_date, ev.end_date, ev.name, ev.expected_uplift_pct)
        for ev in (
            await s.execute(
                select(LocalEvent).where(
                    LocalEvent.tenant_id == tenant_id,
                    LocalEvent.end_date >= start,
                    LocalEvent.start_date <= end,
                    LocalEvent.expected_uplift_pct.is_not(None),
                )
            )
        ).scalars()
    ]

    d = start
    while d <= end:
        own_obs = _latest(obs.get(own_id, {}).get(d, [])) if own_id else None
        own_occ_now = own_obs.occ_mid if own_obs and own_obs.reliable else None
        own_pace = (
            pace(d, own_obs.lead, own_occ_now, own_curves, is_holiday)
            if own_obs
            else Pace(None, 0, None)
        )
        comp_latest = [o for c in comp_ids if (o := _latest(obs.get(c, {}).get(d, [])))]
        reliable_obs = [o for o in comp_latest if o.reliable]
        reliable = [o.occ_mid for o in reliable_obs]
        comp_med = median(reliable) if len(reliable) >= 2 else None
        comp_occ = comp_med.quantize(Q4) if comp_med is not None else None
        lo_med = median(o.occ_low for o in reliable_obs) if len(reliable) >= 2 else None
        hi_med = median(o.occ_high for o in reliable_obs) if len(reliable) >= 2 else None
        comp_curve_now = comp_curves.get(d, {})
        comp_pace = Pace(None, 0, None)
        if comp_curve_now:
            lead = min(comp_curve_now)
            comp_pace = pace(d, lead, comp_curve_now[lead], comp_curves, is_holiday)
        pickups = [p for c in comp_ids if (p := _pickup_7d(obs.get(c, {}).get(d, []))) is not None]

        own_m = metrics.get((own_id, d)) if own_id else None
        comp_m = [
            m for c in comp_ids if (m := metrics.get((c, d))) and m.availability_status != "unknown"
        ]
        # Giá đem so: còn bán, không bị hạn chế số đêm (giá 1 đêm so với giá 1 đêm).
        comp_prices = [
            m.min_price
            for m in comp_m
            if m.min_price is not None
            and m.availability_status == "available"
            and (m.min_stay or 1) == 1
        ]
        own_occ_for_rules = pms[d] if d in pms else own_occ_now
        occ_source = "pms" if d in pms else ("estimate" if own_occ_now is not None else None)
        pace_4w: int | None = None
        capacity: int | None = None
        if d in otb_latest:
            rooms_otb, capacity = otb_latest[d]
            if capacity:
                own_occ_for_rules = (Decimal(rooms_otb) / capacity).quantize(Q4)
                occ_source = "otb"
            lead_now = (d - today).days
            ref_curve = otb_curves.get(d - timedelta(weeks=4), {})
            ref = next((ref_curve[x] for x in (lead_now, lead_now + 1) if x in ref_curve), None)
            pace_4w = rooms_otb - ref if ref is not None else None
        comp_low = sum(
            1
            for m in comp_m
            if m.availability_status == "available"
            and m.exact_rooms_left is not None
            and m.exact_rooms_left <= 3
        )
        comp_median = median(comp_prices) if len(comp_prices) >= 3 else None
        own_price_now = own_m.min_price if own_m else None
        own_index = (
            (own_price_now / comp_median * 100).quantize(Decimal("0.1"))
            if own_price_now and comp_median
            else None
        )
        event = next(((name, up) for a, b, name, up in events if a <= d <= b), None)
        signals = NightSignals(
            stay_date=d,
            days_to_arrival=(d - today).days,
            own_status=own_m.availability_status if own_m else None,
            own_price=own_m.min_price if own_m else None,
            own_rooms_left=own_m.exact_rooms_left if own_m else None,
            own_occ=own_occ_for_rules,
            comp_observed=len(comp_m),
            comp_sold_out=sum(1 for m in comp_m if m.availability_status == "sold_out"),
            comp_median_price=comp_median,
            comp_priced=len(comp_prices),
            comp_occ=comp_occ,
            comp_pace=comp_pace.delta,
            holiday=holidays.get(d),
            comp_low=comp_low,
            own_pace_4w=pace_4w,
            own_capacity=capacity,
            own_occ_source=occ_source,
            event_name=event[0] if event else None,
            event_uplift_pct=event[1] if event else None,
            own_index=own_index,
        )
        sug = suggest(signals, strategy) if d >= today else None
        report.nights.append(
            NightReport(
                stay_date=d,
                days_to_arrival=(d - today).days,
                holiday=holidays.get(d),
                own_obs=own_obs,
                own_pms_occ=pms.get(d),
                own_pace=own_pace,
                own_price=signals.own_price,
                own_status=signals.own_status,
                own_rooms_left=signals.own_rooms_left,
                currency=(own_m.currency if own_m else None)
                or next((m.currency for m in comp_m if m.currency), None),
                comp_observed=signals.comp_observed,
                comp_sold_out=signals.comp_sold_out,
                comp_median_price=signals.comp_median_price,
                comp_occ=comp_occ,
                comp_occ_hotels=len(reliable),
                comp_occ_low=lo_med.quantize(Q4) if lo_med is not None else None,
                comp_occ_high=hi_med.quantize(Q4) if hi_med is not None else None,
                comp_priced=len(comp_prices),
                comp_pickup_7d=sum(pickups) if pickups else None,
                comp_pickup_hotels=len(pickups),
                comp_pace=comp_pace,
                suggestion=sug,
                # Ghi nhận chỉ còn hiệu lực khi gợi ý giữ nguyên mức (đổi mức thì hỏi lại).
                decision=_decision(decisions.get((d, sug.kind)), sug) if sug else None,
            )
        )
        d += timedelta(days=1)

    if own_id:
        pairs = []
        triples: list[tuple[int, Decimal, Decimal]] = []
        for night, real in pms.items():
            if not today - timedelta(days=CALIBRATION_DAYS) <= night < today:
                continue
            own_night = [o for o in obs.get(own_id, {}).get(night, []) if o.reliable]
            last = _latest(own_night)
            if last is not None and last.lead <= LEAD_TOLERANCE + 1:
                pairs.append((last.occ_mid, real))
            # Mỗi nhóm lead time: quan sát gần ngày đến nhất trong nhóm, so với PMS cuối cùng.
            for _name, lo, hi in LEAD_BUCKETS:
                in_bucket = [o for o in own_night if lo <= o.lead <= hi]
                if in_bucket:
                    o = min(in_bucket, key=lambda x: x.lead)
                    triples.append((o.lead, o.occ_mid, real))
        report.calibration = calibrate(pairs)
        report.calibration_by_lead = calibrate_by_lead(triples)
    first = (
        await s.execute(
            select(func.min(OccupancyEstimate.scanned_at)).where(
                OccupancyEstimate.hotel_id.in_(ids), OccupancyEstimate.channel == channel
            )
        )
    ).scalar_one()
    report.data_since = first.date() if first else None
    return report
