"""Song ngữ cho chữ backend sinh ra: email, CSV, lý do gợi ý giá, lỗi URL, tên ngày lễ, thời tiết.

Catalog `locales/<mã>.json` phẳng, khoá theo nhóm (`email.*`, `csv.*`, `price.*`…), tham số kiểu
`str.format` (`{count}`). Thiếu khoá ở một ngôn ngữ thì dùng bản tiếng Việt, thiếu cả hai thì trả
chính khoá. Số nhiều: khoá `x.one` + `x.other`, gọi `t(locale, "x", count=n)` tự chọn dạng.
Dữ liệu (tên khách sạn, nhãn tenant nhập) và `detail` lỗi HTTP không đi qua đây.
"""

import json
from functools import cache
from pathlib import Path

LOCALES = ("vi", "en")
DEFAULT_LOCALE = "vi"

_DIR = Path(__file__).parent / "locales"


@cache
def catalog(locale: str) -> dict[str, str]:
    """Nạp một lần mỗi tiến trình."""
    data: dict[str, str] = json.loads((_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    return data


def normalize_locale(value: str | None) -> str:
    """Mã ngôn ngữ hỗ trợ: "en-GB", "EN", "en_US" -> "en"; mã lạ hoặc rỗng -> tiếng Việt."""
    tag = (value or "").strip().lower().replace("_", "-").split("-")[0]
    return tag if tag in LOCALES else DEFAULT_LOCALE


def parse_accept_language(header: str | None) -> str:
    """Ngôn ngữ hỗ trợ có q cao nhất trong `Accept-Language` ("en-GB,en;q=0.9,vi;q=0.8")."""
    ranked: list[tuple[float, int, str]] = []
    for i, part in enumerate((header or "").split(",")):
        tag, _, rest = part.strip().partition(";")
        q = 1.0
        for param in rest.split(";"):
            name, _, value = param.strip().partition("=")
            if name.strip().lower() == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        primary = tag.strip().lower().replace("_", "-").split("-")[0]
        if q > 0 and primary in LOCALES:
            ranked.append((-q, i, primary))
    return min(ranked)[2] if ranked else DEFAULT_LOCALE


def _lookup(locale: str, key: str) -> str | None:
    return catalog(locale).get(key) or catalog(DEFAULT_LOCALE).get(key)


def has(key: str) -> bool:
    return key in catalog(DEFAULT_LOCALE)


def t(locale: str, key: str, **params: object) -> str:
    count = params.get("count")
    if isinstance(count, int) and not has(key) and has(f"{key}.other"):
        key = f"{key}.one" if count == 1 else f"{key}.other"
    text = _lookup(normalize_locale(locale), key)
    return key if text is None else text.format(**params)
