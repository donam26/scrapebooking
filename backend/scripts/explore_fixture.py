"""In số lượng phần tử khớp từng selector trên một fixture để xác nhận selector còn đúng.

Dùng: uv run python scripts/explore_fixture.py tests/fixtures/html/reverie_2026-10-10.html.gz
      uv run python scripts/explore_fixture.py --emit-expected tests/fixtures/html/reverie_2026-10-10.html.gz
"""

import gzip
import sys
from pathlib import Path

from selectolax.parser import HTMLParser

from app.collector.booking import selectors as S

CHECKS = {
    "ROOM_TABLE": S.ROOM_TABLE,
    "ROOM_ROWS": S.ROOM_ROWS,
    "ROOM_TYPE_CELL": S.ROOM_TYPE_CELL,
    "ROOM_NAME_LINK": S.ROOM_NAME_LINK,
    "ROOM_NAME_TEXT": S.ROOM_NAME_TEXT,
    "OCCUPANCY_CELL": S.OCCUPANCY_CELL,
    "PRICE_CELL": S.PRICE_CELL,
    "PRICE_TEXT": S.PRICE_TEXT,
    "CONDITIONS_CELL": S.CONDITIONS_CELL,
    "ONLY_X_LEFT": S.ONLY_X_LEFT,
    "ROOM_SELECT": S.ROOM_SELECT,
    "SOLD_OUT_MARKERS": S.SOLD_OUT_MARKERS,
    "HOTEL_NAME": S.HOTEL_NAME,
}


def _read(path: str) -> str:
    data = Path(path).read_bytes()
    return (gzip.decompress(data) if path.endswith(".gz") else data).decode("utf-8")


def _stem(path: str) -> Path:
    p = Path(path)
    return p.parent / p.name.split(".html")[0]


def main(path: str) -> None:
    html = _read(path)
    tree = HTMLParser(html)
    print(f"file: {path}  bytes={len(html)}")
    print(f"csrf: {S.extract_csrf_token(html)}")
    m = S.HOTEL_ID_RE.search(html)
    print(f"hotel_id: {m.group(1) if m else None}")
    for name, sel in CHECKS.items():
        nodes = tree.css(sel)
        sample = [n.text(strip=True)[:60] for n in nodes[:3]]
        print(f"{name:18s} {len(nodes):4d}  {sample}")
    for sel in tree.css(S.ROOM_SELECT)[:3]:
        values = [o.attributes.get("value") for o in sel.css("option")]
        print(f"select options: {values}")
    for node in tree.css(S.ONLY_X_LEFT)[:5]:
        print(f"badge text: {node.text(strip=True)!r}")


def emit_expected(path: str) -> None:
    import json

    from app.collector.booking.parser import page_to_dict, parse_hotel_page

    page = parse_hotel_page(_read(path), expected_currency="VND", adults=2)
    out = _stem(path).with_name(_stem(path).name + ".expected.json")
    out.write_text(json.dumps(page_to_dict(page), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}: outcome={page.outcome} offers={len(page.offers)}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--emit-expected":
        emit_expected(sys.argv[2])
    else:
        main(sys.argv[1])
