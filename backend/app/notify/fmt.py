"""Định dạng số, giá, đêm cho email theo ngôn ngữ, cùng cách viết với dashboard: tiếng Việt dấu
chấm hàng nghìn "1.250.000 ₫", "T7 03/10"; tiếng Anh (en-GB) "₫1,250,000", "Sat 03/10".
Thêm ngôn ngữ: thêm một dòng `_STYLES` (thứ viết tắt nằm ở catalog `date.weekday.*`)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.i18n import DEFAULT_LOCALE, normalize_locale, t


@dataclass(frozen=True)
class NumberStyle:
    thousands: str  # dấu nhóm hàng nghìn
    vnd: str  # mẫu tiền đồng, `{amount}` là số đã nhóm


_STYLES = {
    "vi": NumberStyle(thousands=".", vnd="{amount} ₫"),
    "en": NumberStyle(thousands=",", vnd="₫{amount}"),
}


def _style(locale: str) -> NumberStyle:
    return _STYLES.get(normalize_locale(locale), _STYLES[DEFAULT_LOCALE])


def fmt_int(n: int | Decimal, locale: str = DEFAULT_LOCALE) -> str:
    return f"{int(n):,}".replace(",", _style(locale).thousands)


def fmt_money(
    value: Decimal | str | None, currency: str | None, locale: str = DEFAULT_LOCALE
) -> str:
    if value is None:
        return "—"
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        return str(value)
    text = fmt_int(amount.quantize(Decimal(1)), locale)
    if currency in (None, "VND"):
        return _style(locale).vnd.format(amount=text)
    return f"{text} {currency}"


def fmt_night(d: date, locale: str = DEFAULT_LOCALE) -> str:
    """Đêm dạng "T7 03/10" / "Sat 03/10"."""
    return f"{t(locale, f'date.weekday.{d.weekday()}')} {d.day:02d}/{d.month:02d}"


def fmt_pct(value: Decimal | float | int) -> str:
    """Phần trăm làm tròn, không dấu: "12%"."""
    return f"{abs(round(float(value))):d}%"
