import re
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from typing import Any

from selectolax.parser import HTMLParser, Node

from app.collector.booking import selectors as S
from app.domain.models import PageOutcome, ParsedPage, RatePlan, RoomOffer

_SYMBOLS: dict[str, str] = {
    "US$": "USD", "$": "USD", "€": "EUR", "£": "GBP", "₫": "VND", "฿": "THB",
    "¥": "JPY", "₩": "KRW", "zł": "PLN", "S$": "SGD", "RM": "MYR", "Rp": "IDR", "₱": "PHP",
}  # fmt: skip
_NUMBER_RE = re.compile(r"\d[\d.,\s ]*\d|\d")
_CODE_RE = re.compile(r"\b([A-Z]{3})\b")


def parse_price(text: str, fallback_currency: str) -> tuple[Decimal, str] | None:
    cleaned = text.replace(" ", " ").strip()
    m = _NUMBER_RE.search(cleaned)
    if not m:
        return None
    raw = re.sub(r"\s", "", m.group(0))
    if "," in raw and "." in raw:
        dec_sep = "," if raw.rfind(",") > raw.rfind(".") else "."
        raw = raw.replace("." if dec_sep == "," else ",", "").replace(dec_sep, ".")
    elif "," in raw:
        parts = raw.split(",")
        raw = raw.replace(",", "") if all(len(p) == 3 for p in parts[1:]) else raw.replace(",", ".")
    elif "." in raw:
        parts = raw.split(".")
        raw = raw.replace(".", "") if all(len(p) == 3 for p in parts[1:]) else raw
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    currency = fallback_currency
    code = _CODE_RE.search(cleaned)
    if code:
        currency = code.group(1)
    else:
        for symbol, iso in sorted(_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
            if symbol in cleaned:
                currency = iso
                break
    return value, currency


def _text(node: Node | None) -> str:
    return " ".join(node.text(separator=" ").split()) if node is not None else ""


def _dropdown_max(row: Node) -> int | None:
    select = row.css_first(S.ROOM_SELECT)
    if select is None:
        return None
    values: list[int] = []
    for opt in select.css("option"):
        v = opt.attributes.get("value")
        if v is not None and v.strip().isdigit():
            values.append(int(v))
    return max(values) if values else None


def _badge_count(row: Node) -> int | None:
    for node in row.css(S.ONLY_X_LEFT):
        m = S.ONLY_X_LEFT_RE.search(_text(node))
        if m:
            return int(m.group(1))
    m = S.ONLY_X_LEFT_RE.search(_text(row))
    return int(m.group(1)) if m else None


def _rate_plan(row: Node, expected_currency: str, default_persons: int | None) -> RatePlan | None:
    price_node = row.css_first(S.PRICE_TEXT)
    parsed = parse_price(_text(price_node), expected_currency) if price_node is not None else None
    if parsed is None:
        return None
    price, currency = parsed
    conditions = _text(row.css_first(S.CONDITIONS_CELL)).lower()
    refundable: bool | None
    if "non-refundable" in conditions or "non refundable" in conditions:
        refundable = False
    elif "free cancellation" in conditions:
        refundable = True
    elif "total cost to cancel" in conditions:  # đã qua hạn huỷ miễn phí (nhận phòng trong ngày)
        refundable = False
    else:
        refundable = None
    breakfast: bool | None = True if "breakfast included" in conditions else None
    name = (
        "Non-refundable"
        if refundable is False
        else ("Free cancellation" if refundable else "Standard")
    )
    if breakfast:
        name += " + breakfast"
    return RatePlan(
        name=name,
        price=price,
        currency=currency,
        refundable=refundable,
        breakfast=breakfast,
        max_persons=_max_occupancy(row) or default_persons,
    )


def _is_partner_offer(row: Node) -> bool:
    return S.PARTNER_BLOCK_MARKER in (row.attributes.get("data-block-id") or "")


def _room_id(type_cell: Node | None, own_rows: list[Node]) -> str | None:
    """data-room-id của link loại phòng; không có thì tiền tố số của block id ở dòng giá của chính
    khách sạn (dòng đối tác "bbasic_0" không mang ID loại phòng)."""
    link = type_cell.css_first(S.ROOM_NAME_LINK) if type_cell is not None else None
    if link is not None and link.attributes.get("data-room-id"):
        return str(link.attributes["data-room-id"])
    for row in own_rows:
        prefix = (row.attributes.get("data-block-id") or "").split("_", 1)[0]
        if prefix.isdigit():
            return prefix
    return None


def _max_occupancy(row: Node) -> int | None:
    cell = row.css_first(S.OCCUPANCY_CELL)
    if cell is None:
        return None
    attr = cell.attributes.get("data-max-occupancy")
    if attr and attr.isdigit():
        return int(attr)
    m = S.MAX_PEOPLE_RE.search(_text(cell))
    return int(m.group(1)) if m else None


def _roomtype_occupancy(type_cell: Node | None) -> int | None:
    node = type_cell.css_first(S.ROOMTYPE_OCCUPANCY) if type_cell is not None else None
    m = S.SLEEPS_ADULTS_RE.search(_text(node)) if node is not None else None
    return int(m.group(1)) if m else None


def _hotel_name(tree: HTMLParser) -> str | None:
    for selector in S.HOTEL_NAME_PRIORITY:
        name = _text(tree.css_first(selector))
        if name:
            return name
    return None


def parse_hotel_page(html: str, expected_currency: str, adults: int | None = None) -> ParsedPage:
    """`adults`: số người lớn đã tìm; dòng giá cho ít khách hơn (VD "Only for 1 guest") bị bỏ để
    giá thấp nhất so sánh được giữa các khách sạn. None: giữ mọi dòng."""
    tree = HTMLParser(html)
    hotel_id_match = S.HOTEL_ID_RE.search(html)
    booking_hotel_id = hotel_id_match.group(1) if hotel_id_match else None
    hotel_name = _hotel_name(tree)
    csrf = S.extract_csrf_token(html)

    rows = tree.css(S.ROOM_ROWS)
    if not rows:
        outcome = PageOutcome.SOLD_OUT if tree.css_first(S.SOLD_OUT_MARKERS) else PageOutcome.EMPTY
        return ParsedPage(outcome, booking_hotel_id, hotel_name, csrf, ())

    groups: list[dict[str, Any]] = []
    for row in rows:
        type_cell = row.css_first(S.ROOM_TYPE_CELL)
        if type_cell is not None or not groups:
            groups.append(
                {
                    "type_cell": type_cell,
                    "name": _text(row.css_first(S.ROOM_NAME_TEXT)) or _text(type_cell),
                    "occupancy": _max_occupancy(row) or _roomtype_occupancy(type_cell),
                    "rows": [row],
                }
            )
        else:
            groups[-1]["rows"].append(row)

    offers: list[RoomOffer] = []
    for g in groups:
        # Chỉ tính dòng giá của chính khách sạn; nhóm chỉ có giá đối tác thì bỏ.
        own_rows = [row for row in g["rows"] if not _is_partner_offer(row)]
        room_id = _room_id(g["type_cell"], own_rows)
        if not own_rows or not room_id or not g["name"]:
            continue
        rates = tuple(
            r
            for r in (_rate_plan(row, expected_currency, g["occupancy"]) for row in own_rows)
            if r and (adults is None or r.max_persons is None or r.max_persons >= adults)
        )
        # Nhãn "We have N left" ở ô loại phòng (tín hiệu cả loại phòng) hoặc ở ô điều kiện.
        badge_sources = [g["type_cell"], *own_rows] if g["type_cell"] is not None else own_rows
        badge = next((b for b in map(_badge_count, badge_sources) if b is not None), None)
        dropdowns = [d for d in (_dropdown_max(row) for row in own_rows) if d is not None]
        offers.append(
            RoomOffer(
                booking_room_id=room_id,
                name=g["name"],
                max_occupancy=g["occupancy"],
                badge_count=badge,
                dropdown_max=max(dropdowns) if dropdowns else None,
                rates=rates,
            )
        )
    outcome = PageOutcome.ROOMS if offers else PageOutcome.EMPTY
    return ParsedPage(outcome, booking_hotel_id, hotel_name, csrf, tuple(offers))


def page_to_dict(page: ParsedPage) -> dict[str, Any]:
    """Dạng JSON-hoá được của ParsedPage (tuple -> list, Decimal -> str) để so golden."""
    d = asdict(page)
    d["outcome"] = str(page.outcome)
    d["offers"] = [
        {**offer, "rates": [{**rate, "price": str(rate["price"])} for rate in offer["rates"]]}
        for offer in d["offers"]
    ]
    return d
