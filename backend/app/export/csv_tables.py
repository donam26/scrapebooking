"""Bảng CSV tải về cho chủ khách sạn (hàm thuần): tiêu đề cột và nhãn theo ngôn ngữ người tải
(catalog `csv.*`), số không định dạng hàng nghìn để Excel hiểu là số, UTF-8 có BOM để Excel trên
Windows mở đúng dấu tiếng Việt. Nhãn khớp với dashboard (`dashboard/src/messages/*/labels.json`)."""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, tzinfo
from decimal import Decimal

from app.api.schemas import EventOut, OverviewOut
from app.channels.registry import channel_name
from app.i18n import DEFAULT_LOCALE, has, t

_OVERVIEW_COLUMNS = (
    "channel",
    "hotel",
    "role",
    "night",
    "weekday",
    "status",
    "rooms_left",
    "min_price",
    "currency",
    "comp_sold_out",
    "comp_observed",
    "comp_median",
    "price_vs_median",
    "price_rank",
    "priced_hotels",
    "holiday",
)

_EVENTS_COLUMNS = (
    "observed_at",
    "channel",
    "hotel",
    "room_type",
    "night",
    "event",
    "before",
    "after",
    "change",
)


def overview_header(locale: str = DEFAULT_LOCALE) -> tuple[str, ...]:
    return tuple(t(locale, f"csv.header.{c}") for c in _OVERVIEW_COLUMNS)


def events_header(locale: str = DEFAULT_LOCALE) -> tuple[str, ...]:
    return tuple(t(locale, f"csv.header.{c}") for c in _EVENTS_COLUMNS)


def _label(locale: str, group: str, code: str) -> str:
    """Nhãn của mã backend; mã lạ giữ nguyên."""
    key = f"csv.{group}.{code}"
    return t(locale, key) if has(key) else code


def weekday_short(d: date, locale: str = DEFAULT_LOCALE) -> str:
    """Thứ viết tắt: "T7" / "Sat"."""
    return t(locale, f"date.weekday.{d.weekday()}")


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _text(v: str | None) -> str:
    """Ô chữ từ nguồn ngoài (tên trên Booking, nhãn tenant nhập): thêm dấu ' trước ký tự mở đầu
    công thức để Excel không chạy công thức (CSV injection). Ô số không đi qua hàm này."""
    s = v or ""
    return "'" + s if s.startswith(_FORMULA_START) else s


def _num(v: Decimal | int | None, currency: str | None = None) -> str:
    if v is None:
        return ""
    if isinstance(v, int):
        return str(v)
    if currency == "VND":
        return str(v.quantize(Decimal(1)))
    return format(v.normalize(), "f")


def to_csv(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    return "﻿" + buf.getvalue()


def overview_rows(
    data: OverviewOut, names: dict[int, str], locale: str = DEFAULT_LOCALE
) -> list[list[str]]:
    """Mỗi hàng một (khách sạn, đêm); các cột thị trường lặp lại cho mọi khách sạn của đêm đó.
    Tên ngày lễ đã theo ngôn ngữ trong `data`."""
    compset = {c.stay_date: c for c in data.compset}
    holidays = {h.date: h.name for h in data.holidays}
    rows: list[list[str]] = []
    for h in data.hotels:
        for cell in h.cells:
            c = compset.get(cell.stay_date)
            idx = c.price_index if c else None
            rows.append(
                [
                    channel_name(data.channel),
                    _text(names.get(h.hotel.id) or h.label or h.hotel.name or f"#{h.hotel.id}"),
                    _label(locale, "role", h.role),
                    cell.stay_date.isoformat(),
                    weekday_short(cell.stay_date, locale),
                    _label(locale, "status", cell.availability_status or "not_scanned"),
                    _num(cell.exact_rooms_left),
                    _num(cell.min_price, cell.currency),
                    cell.currency or "",
                    _num(c.competitors_sold_out) if c else "",
                    _num(c.competitors_observed) if c else "",
                    _num(c.median_price, c.currency) if c else "",
                    _num((idx - 100).quantize(Decimal(1))) if idx is not None else "",
                    _num(c.own_rank) if c else "",
                    _num(c.priced_hotels) if c and c.priced_hotels else "",
                    _text(holidays.get(cell.stay_date)),
                ]
            )
    return rows


def events_rows(
    events: list[EventOut], names: dict[int, str], tz: tzinfo, locale: str = DEFAULT_LOCALE
) -> list[list[str]]:
    """Thời điểm quan sát theo giờ địa phương của tenant."""
    rows: list[list[str]] = []
    for e in events:
        rows.append(
            [
                e.observed_at.astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                channel_name(e.channel),
                _text(names.get(e.hotel_id) or e.hotel_name or f"#{e.hotel_id}"),
                _text(e.room_type_name) or t(locale, "csv.whole_hotel"),
                e.stay_date.isoformat(),
                _label(locale, "event", e.event_type),
                _text(e.from_value),
                _text(e.to_value),
                _num(e.delta),
            ]
        )
    return rows


def truncated_row(limit: int, locale: str = DEFAULT_LOCALE) -> list[str]:
    """Dòng cuối khi cắt bớt: nói rõ và cách lấy phần còn lại."""
    return [t(locale, "csv.truncated", max=limit)] + [""] * (len(_EVENTS_COLUMNS) - 1)


def filename(kind: str, today: date, locale: str = DEFAULT_LOCALE) -> str:
    """`kind`: overview | events."""
    return f"scrapebooking-{t(locale, f'csv.file.{kind}')}-{today.isoformat()}.csv"
