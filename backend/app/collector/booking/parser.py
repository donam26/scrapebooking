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
    return node.text(separator=" ", strip=True) if node is not None else ""


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


def _rate_plan(row: Node, expected_currency: str) -> RatePlan | None:
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
        name=name, price=price, currency=currency, refundable=refundable, breakfast=breakfast
    )


def _room_id(row: Node) -> str | None:
    link = row.css_first(S.ROOM_NAME_LINK)
    if link is not None and link.attributes.get("data-room-id"):
        return str(link.attributes["data-room-id"])
    block = row.attributes.get("data-block-id") or ""
    return block.split("_", 1)[0] or None


def _max_occupancy(row: Node) -> int | None:
    cell = row.css_first(S.OCCUPANCY_CELL)
    if cell is None:
        return None
    attr = cell.attributes.get("data-max-occupancy")
    if attr and attr.isdigit():
        return int(attr)
    m = S.MAX_PEOPLE_RE.search(_text(cell))
    return int(m.group(1)) if m else None


def parse_hotel_page(html: str, expected_currency: str) -> ParsedPage:
    tree = HTMLParser(html)
    hotel_id_match = S.HOTEL_ID_RE.search(html)
    booking_hotel_id = hotel_id_match.group(1) if hotel_id_match else None
    hotel_name = _text(tree.css_first(S.HOTEL_NAME)) or None
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
                    "id": _room_id(row),
                    "name": _text(row.css_first(S.ROOM_NAME_TEXT)) or _text(type_cell),
                    "occupancy": _max_occupancy(row),
                    "rows": [row],
                }
            )
        else:
            groups[-1]["rows"].append(row)

    offers: list[RoomOffer] = []
    for g in groups:
        if not g["id"] or not g["name"]:
            continue
        rates = tuple(r for r in (_rate_plan(row, expected_currency) for row in g["rows"]) if r)
        badge = next((b for b in (_badge_count(row) for row in g["rows"]) if b is not None), None)
        dropdowns = [d for d in (_dropdown_max(row) for row in g["rows"]) if d is not None]
        offers.append(
            RoomOffer(
                booking_room_id=g["id"],
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
