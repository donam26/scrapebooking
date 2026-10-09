"""OTB (on the books) của khách sạn của bạn theo ngày (roadmap 5.1–5.3) — hàm thuần.

Hai cách nhập:
1. **Báo cáo OTB theo ngày** (mỗi dòng: đêm, phòng đã đặt, doanh thu, phòng sẵn có; tuỳ chọn ngày
   chụp, huỷ, phòng đoàn). Ngày chụp mặc định là ngày tải lên.
2. **File đặt phòng chi tiết** (ngày đặt, ngày đến, ngày đi, ngày huỷ, trạng thái, số phòng, doanh
   thu): dựng lại bản chụp OTB cho cả quá khứ, nên có pickup/pace/STLY ngay từ ngày đầu.

Chỉ số (chuẩn HSMAI/OPERA):
- Pickup = thay đổi ròng của OTB giữa hai lần đo (1 ngày, 7 ngày).
- Pace = OTB "tính đến ngày" so với kỳ tham chiếu ở CÙNG số ngày trước khi đến: 4 tuần trước (cùng
  thứ) và cùng kỳ năm trước (STLY = đêm cách 364 ngày, cùng thứ).
- Dự báo đơn giản: OTB hiện tại + pickup lịch sử trung bình từ lead time này tới ngày đến của các
  đêm cùng thứ (additive pickup, Weatherford & Kimes), chặn bởi số phòng sẵn có.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.pms.base import RowError, Table
from app.pms.csv_adapter import _norm, parse_date, parse_decimal, parse_int

MAX_LEAD = 120  # bản chụp dựng lại từ file đặt phòng: tới 120 ngày trước khi đến

_OTB_ALIASES: dict[str, tuple[str, ...]] = {
    "as_of_date": ("as_of_date", "as of", "as of date", "report date", "ngày chụp", "ngày báo cáo"),
    "stay_date": ("stay_date", "date", "stay date", "ngày", "ngày ở", "business date", "night"),
    "rooms_otb": (
        "rooms_otb", "otb", "rooms on books", "on the books", "phòng đã đặt", "rooms sold",
        "room nights", "booked", "đã đặt",
    ),
    "revenue_otb": ("revenue_otb", "revenue", "room revenue", "doanh thu", "doanh thu phòng"),
    "rooms_available": (
        "rooms_available", "capacity", "available rooms", "phòng sẵn có", "rooms available",
        "tổng phòng", "total rooms",
    ),
    "cancellations": ("cancellations", "cancelled", "huỷ", "hủy", "số huỷ"),
    "group_rooms": ("group_rooms", "group", "đoàn", "phòng đoàn", "block"),
}  # fmt: skip

_BOOKING_ALIASES: dict[str, tuple[str, ...]] = {
    "booking_date": (
        "booking_date", "booked on", "created", "created at", "ngày đặt", "ngày tạo",
        "booking date",
    ),
    "arrival": ("arrival", "check in", "check-in", "checkin", "ngày đến", "từ ngày"),
    "departure": ("departure", "check out", "check-out", "checkout", "ngày đi", "đến ngày"),
    "cancel_date": ("cancel_date", "cancelled on", "cancellation date", "ngày huỷ", "ngày hủy"),
    "status": ("status", "trạng thái", "state"),
    "rooms": ("rooms", "số phòng", "room count", "qty"),
    "revenue": ("revenue", "total", "room revenue", "doanh thu", "tiền phòng", "amount"),
    "group": ("group", "đoàn", "is group", "block"),
}  # fmt: skip

_CANCELLED = re.compile(r"cancel|huỷ|hủy|no.?show", re.I)


def suggest(columns: list[str], aliases: Mapping[str, tuple[str, ...]]) -> dict[str, str]:
    normalised = {_norm(c): c for c in columns}
    out: dict[str, str] = {}
    for canonical, names in aliases.items():
        for alias in names:
            if _norm(alias) in normalised:
                out[canonical] = normalised[_norm(alias)]
                break
    return out


def suggest_otb_mapping(columns: list[str]) -> dict[str, str]:
    return suggest(columns, _OTB_ALIASES)


def suggest_booking_mapping(columns: list[str]) -> dict[str, str]:
    return suggest(columns, _BOOKING_ALIASES)


@dataclass(frozen=True)
class OtbRow:
    as_of_date: date
    stay_date: date
    rooms_otb: int
    revenue_otb: Decimal | None = None
    rooms_available: int | None = None
    cancellations: int | None = None
    group_rooms: int | None = None


@dataclass(frozen=True)
class Booking:
    booking_date: date
    arrival: date
    departure: date
    rooms: int = 1
    revenue: Decimal | None = None  # tổng tiền phòng cả đặt phòng (mọi phòng, mọi đêm)
    cancel_date: date | None = None
    group: bool = False

    @property
    def nights(self) -> int:
        return max(1, (self.departure - self.arrival).days)


def _get(raw: Mapping[str, Any], mapping: Mapping[str, str], col: str) -> Any:
    src = mapping.get(col)
    v = raw.get(src) if src else None
    return None if v in ("", None) else v


def parse_otb_report(
    table: Table, mapping: Mapping[str, str], as_of_default: date
) -> tuple[list[OtbRow], list[RowError]]:
    rows: list[OtbRow] = []
    errors: list[RowError] = []
    for i, raw in enumerate(table.rows, start=2):
        try:
            stay = parse_date(_get(raw, mapping, "stay_date"))
            otb = parse_int(_get(raw, mapping, "rooms_otb"))
            if otb is None or otb < 0:
                raise ValueError("rooms_otb missing or negative")
            as_of_raw = _get(raw, mapping, "as_of_date")
            rows.append(
                OtbRow(
                    as_of_date=parse_date(as_of_raw) if as_of_raw is not None else as_of_default,
                    stay_date=stay,
                    rooms_otb=otb,
                    revenue_otb=parse_decimal(_get(raw, mapping, "revenue_otb"), money=True),
                    rooms_available=parse_int(_get(raw, mapping, "rooms_available")),
                    cancellations=parse_int(_get(raw, mapping, "cancellations")),
                    group_rooms=parse_int(_get(raw, mapping, "group_rooms")),
                )
            )
        except (ValueError, TypeError) as exc:
            errors.append(RowError(i - 1, None, str(exc)[:200]))
    return rows, errors


def _truthy(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "x", "có", "co", "group", "đoàn")


def parse_bookings(
    table: Table, mapping: Mapping[str, str]
) -> tuple[list[Booking], list[RowError]]:
    out: list[Booking] = []
    errors: list[RowError] = []
    for i, raw in enumerate(table.rows, start=2):
        try:
            arrival = parse_date(_get(raw, mapping, "arrival"))
            departure = parse_date(_get(raw, mapping, "departure"))
            if departure <= arrival:
                raise ValueError("departure must be after arrival")
            booked = parse_date(_get(raw, mapping, "booking_date"))
            cancel_raw = _get(raw, mapping, "cancel_date")
            cancel = parse_date(cancel_raw) if cancel_raw is not None else None
            status = str(_get(raw, mapping, "status") or "")
            if cancel is None and _CANCELLED.search(status):
                cancel = booked  # huỷ không rõ ngày: coi như chưa từng có trong OTB
            out.append(
                Booking(
                    booking_date=booked,
                    arrival=arrival,
                    departure=departure,
                    rooms=parse_int(_get(raw, mapping, "rooms")) or 1,
                    revenue=parse_decimal(_get(raw, mapping, "revenue"), money=True),
                    cancel_date=cancel,
                    group=_truthy(_get(raw, mapping, "group")),
                )
            )
        except (ValueError, TypeError) as exc:
            errors.append(RowError(i - 1, None, str(exc)[:200]))
    return out, errors


def rebuild_snapshots(
    bookings: Iterable[Booking],
    today: date,
    rooms_available: int | None = None,
    max_lead: int = MAX_LEAD,
) -> list[OtbRow]:
    """Dựng bản chụp OTB (as_of, stay) từ file đặt phòng: phòng đặt trước hoặc trong ngày `as_of`
    và chưa huỷ tính đến hết `as_of`. Chỉ các mốc 0..max_lead ngày trước khi đến, as_of ≤ today."""
    # Sự kiện theo đêm: (ngày có hiệu lực, Δphòng, Δdoanh thu, Δhuỷ, Δđoàn).
    deltas: dict[date, list[tuple[date, int, Decimal, int, int]]] = defaultdict(list)
    for b in bookings:
        per_night = (b.revenue / b.nights) if b.revenue is not None else Decimal(0)
        d = b.arrival
        while d < b.departure:
            g = b.rooms if b.group else 0
            # `revenue` là tổng tiền phòng của cả đặt phòng (mọi phòng, mọi đêm).
            deltas[d].append((b.booking_date, b.rooms, per_night, 0, g))
            if b.cancel_date is not None:
                deltas[d].append((b.cancel_date, -b.rooms, -per_night, b.rooms, -g))
            d += timedelta(days=1)
    out: list[OtbRow] = []
    for stay, evs in deltas.items():
        evs.sort(key=lambda e: e[0])
        first_as_of = stay - timedelta(days=max_lead)
        last_as_of = min(stay, today)
        rooms = cxl = grp = 0
        rev = Decimal(0)
        i = 0
        as_of = min(first_as_of, last_as_of)
        # Cộng dồn sự kiện trước mốc đầu.
        while i < len(evs) and evs[i][0] < as_of:
            rooms, rev, cxl, grp = (
                rooms + evs[i][1],
                rev + evs[i][2],
                cxl + evs[i][3],
                grp + evs[i][4],
            )
            i += 1
        while as_of <= last_as_of:
            while i < len(evs) and evs[i][0] <= as_of:
                rooms, rev = rooms + evs[i][1], rev + evs[i][2]
                cxl, grp = cxl + evs[i][3], grp + evs[i][4]
                i += 1
            if rooms or cxl:
                out.append(
                    OtbRow(
                        as_of,
                        stay,
                        max(0, rooms),
                        rev.quantize(Decimal("0.01")),
                        rooms_available,
                        cxl,
                        max(0, grp) or None,
                    )
                )
            as_of += timedelta(days=1)
    return out


# ---- chỉ số ------------------------------------------------------------------------------------


Curves = Mapping[date, Mapping[int, int]]  # đêm -> {lead (ngày trước khi đến) -> phòng OTB}


def build_curves(rows: Iterable[tuple[date, date, int]]) -> dict[date, dict[int, int]]:
    """(as_of, stay, rooms_otb) → đường OTB theo lead time của từng đêm."""
    out: dict[date, dict[int, int]] = defaultdict(dict)
    for as_of, stay, rooms in rows:
        lead = (stay - as_of).days
        if lead >= 0:
            out[stay][lead] = rooms
    return out


def otb_at(curve: Mapping[int, int], lead: int, tolerance: int = 1) -> int | None:
    """OTB của một đêm ở `lead` ngày trước khi đến; thiếu bản chụp đúng ngày thì lấy mốc gần nhất
    trước đó (lead lớn hơn, tới `tolerance` ngày) — OTB chỉ đổi khi có đặt/huỷ."""
    for off in range(tolerance + 1):
        if lead + off in curve:
            return curve[lead + off]
    return None


@dataclass(frozen=True)
class OtbNight:
    stay_date: date
    lead: int
    rooms_otb: int | None
    pickup_1d: int | None
    pickup_7d: int | None
    # Pace: OTB hôm nay − OTB của đêm tham chiếu ở cùng lead (4 tuần trước cùng thứ; STLY 364 ngày).
    pace_4w: int | None
    ref_4w: int | None
    stly: int | None
    pace_stly: int | None
    forecast_rooms: int | None
    forecast_basis: int  # số đêm lịch sử dùng để dự báo


def forecast_pickup(
    curves: Curves, stay: date, lead: int, max_refs: int = 8
) -> tuple[int | None, int]:
    """Pickup lịch sử trung bình từ `lead` tới ngày đến của các đêm cùng thứ đã qua (đủ đường)."""
    pickups = []
    for w in range(1, 53):
        ref = stay - timedelta(weeks=w)
        c = curves.get(ref)
        if not c or 0 not in c:
            continue
        at = otb_at(c, lead)
        if at is None:
            continue
        pickups.append(c[0] - at)
        if len(pickups) >= max_refs:
            break
    if not pickups:
        return None, 0
    return round(sum(pickups) / len(pickups)), len(pickups)


def otb_night(curves: Curves, stay: date, today: date, capacity: int | None = None) -> OtbNight:
    lead = (stay - today).days
    curve = curves.get(stay, {})
    now = otb_at(curve, lead) if lead >= 0 else curve.get(0)
    d1 = otb_at(curve, lead + 1) if now is not None else None
    d7 = otb_at(curve, lead + 7) if now is not None else None
    ref = curves.get(stay - timedelta(weeks=4), {})
    ref_4w = otb_at(ref, lead) if lead >= 0 else None
    ly = curves.get(stay - timedelta(days=364), {})
    stly = otb_at(ly, lead) if lead >= 0 else None
    fc, basis = (None, 0)
    forecast: int | None = None
    if now is not None and lead > 0:
        fc, basis = forecast_pickup(curves, stay, lead)
        if fc is not None:
            forecast = max(now, now + fc)
            if capacity:
                forecast = min(forecast, capacity)
    elif now is not None:
        forecast = now
    return OtbNight(
        stay,
        lead,
        now,
        now - d1 if now is not None and d1 is not None else None,
        now - d7 if now is not None and d7 is not None else None,
        now - ref_4w if now is not None and ref_4w is not None else None,
        ref_4w,
        stly,
        now - stly if now is not None and stly is not None else None,
        forecast,
        basis,
    )


@dataclass(frozen=True)
class Kpis:
    """Chỉ số thật của bạn (chuẩn STR): công suất, ADR, RevPAR trên các đêm có số."""

    nights: int
    rooms_sold: int
    rooms_available: int
    revenue: Decimal
    occupancy_pct: Decimal | None
    adr: Decimal | None
    revpar: Decimal | None


def kpis(rows: Iterable[tuple[int | None, int | None, Decimal | None]]) -> Kpis:
    """(phòng bán, phòng sẵn có, doanh thu phòng) mỗi đêm → Occ = bán/sẵn có; ADR = doanh thu/bán;
    RevPAR = doanh thu/sẵn có (cùng mẫu số, chỉ các đêm có đủ số)."""
    n = sold = avail = 0
    rev = Decimal(0)
    for s, a, r in rows:
        if s is None or not a or r is None:
            continue
        n, sold, avail, rev = n + 1, sold + s, avail + a, rev + r
    q = Decimal("0.01")
    return Kpis(
        n,
        sold,
        avail,
        rev,
        (Decimal(sold) / avail * 100).quantize(Decimal("0.1")) if avail else None,
        (rev / sold).quantize(q) if sold else None,
        (rev / avail).quantize(q) if avail else None,
    )
