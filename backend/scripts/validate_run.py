"""Kiểm chứng một scan run: đối chiếu snapshot trong DB với HTML thô (MinIO), trích độc lập.

Trích bằng selector/regex riêng (KHÔNG dùng app/collector/booking/parser.py), theo đúng quy tắc sản
phẩm: bỏ giá đối tác "Booking Basic", chỉ lấy giá cho số người lớn đã tìm, tồn kho từ nhãn
"We have N left" hoặc dropdown (chạm trần PAGE_DROPDOWN_CAP = "ít nhất"). Lệch nghĩa là parser hoặc
selector cần xem lại (thường do Booking đổi giao diện).

Dùng: cd backend && uv run python scripts/validate_run.py <scan_run_id>
"""

import asyncio
import re
import sys
from collections import Counter
from decimal import Decimal
from typing import Any

from selectolax.parser import HTMLParser
from sqlalchemy import text

from app.collector.storage import S3RawStore
from app.config import get_settings
from app.db.engine import make_engine

_LEFT_RE = re.compile(r"We have (\d+) left|Only (\d+) (?:rooms? )?left", re.I)


def _money(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s))


def _first_int(m: re.Match[str] | None) -> int | None:
    return int(next(g for g in m.groups() if g)) if m else None


def extract(html: str, adults: int) -> dict[str, Any]:
    t = HTMLParser(html)
    checkin = re.search(r'name="checkin" value="([^"]*)"', html)
    shown = checkin.group(1) if checkin else None
    if t.css_first("#no_availability_msg"):
        return {"outcome": "sold_out", "checkin": shown, "rooms": {}}
    groups: list[dict[str, Any]] = []
    for tr in t.css("#hprt-table tbody tr"):
        th = tr.css_first("th")
        if th is not None and "hprt-table-cell-roomtype" in (th.attributes.get("class") or ""):
            link = th.css_first("a[data-room-id]")
            sleeps = th.css_first(".hprt-roomtype-occupancy-info")
            sm = re.search(r"(\d+)\s*adult", sleeps.text()) if sleeps is not None else None
            groups.append(
                {
                    "id": link.attributes.get("data-room-id") if link is not None else None,
                    "badge": _first_int(_LEFT_RE.search(th.text(separator=" "))),
                    "sleeps": int(sm.group(1)) if sm else None,
                    "own": [],
                }
            )
        block = tr.attributes.get("data-block-id")
        if not block or not groups or "bbasic" in block:
            continue
        groups[-1]["own"].append(tr)
    rooms: dict[str, dict[str, Any]] = {}
    for g in groups:
        if not g["own"]:
            continue
        rid = g["id"] or next(
            (
                r.attributes["data-block-id"].split("_")[0]
                for r in g["own"]
                if r.attributes["data-block-id"].split("_")[0].isdigit()
            ),
            None,
        )
        badge, dropdown, prices = g["badge"], 0, []
        for tr in g["own"]:
            if badge is None:
                badge = _first_int(_LEFT_RE.search(tr.text(separator=" ")))
            cell = tr.css_first("td.hprt-table-cell-occupancy")
            occ = (
                int(re.search(r"(\d+)", cell.text()).group(1)) if cell is not None else g["sleeps"]
            )
            price = tr.css_first("td.hprt-table-cell-price span.prco-valign-middle-helper")
            opts = [
                int(o.attributes["value"])
                for o in tr.css("select option")
                if (o.attributes.get("value") or "").isdigit()
            ]
            dropdown = max([dropdown, *opts])
            if price is not None and (occ is None or occ >= adults):
                prices.append(_money(price.text()))
        if rid:
            rooms[rid] = {
                "badge": badge,
                "dropdown": dropdown,
                "min_price": min(prices) if prices else None,
            }
    return {"outcome": "rooms" if rooms else "empty", "checkin": shown, "rooms": rooms}


def expected_stock(badge: int | None, dropdown: int, cap: int) -> tuple[int | None, str]:
    if badge is not None:
        return badge, "exact"
    if dropdown >= cap:
        return dropdown, "capped"
    return None, "hidden"


async def main(run_id: int) -> int:
    s = get_settings()
    store = S3RawStore(s.minio_bucket, s.minio_endpoint, s.minio_access_key, s.minio_secret_key)
    engine = make_engine(s.database_url)
    async with engine.connect() as c:
        probes = (
            await c.execute(
                text(
                    "select p.id, h.booking_slug, p.stay_date, p.status, p.adults, p.raw_object_key "
                    "from probes p join hotels h on h.id = p.hotel_id where p.scan_run_id = :r "
                    "order by h.booking_slug, p.stay_date"
                ),
                {"r": run_id},
            )
        ).all()
        snaps = (
            await c.execute(
                text(
                    "select rs.probe_id, rt.booking_room_id, rs.rooms_left, rs.stock_confidence, rs.min_price "
                    "from room_snapshots rs join room_types rt on rt.id = rs.room_type_id "
                    "join probes p on p.id = rs.probe_id where p.scan_run_id = :r"
                ),
                {"r": run_id},
            )
        ).all()
    await engine.dispose()
    db: dict[int, dict[str, tuple[Any, ...]]] = {}
    for pid, rid, left, conf, price in snaps:
        db.setdefault(pid, {})[rid] = (left, conf, price)
    stats: Counter[str] = Counter()
    problems: list[str] = []
    for pid, slug, stay, status, adults, key in probes:
        stats[f"probe:{status}"] += 1
        html = await store.get_html(key) if key else None
        if html is None or status not in ("ok", "sold_out", "no_rooms_1n"):
            continue
        page = extract(html, adults)
        expected_status = {"rooms": "ok", "sold_out": "sold_out", "empty": "no_rooms_1n"}[
            page["outcome"]
        ]
        if page["checkin"] != stay.isoformat() or expected_status != status:
            problems.append(
                f"{slug} {stay}: db={status} html={page['outcome']} checkin={page['checkin']}"
            )
            continue
        if set(db.get(pid, {})) != set(page["rooms"]):
            problems.append(
                f"{slug} {stay}: room ids db={sorted(db.get(pid, {}))} html={sorted(page['rooms'])}"
            )
        for rid, room in page["rooms"].items():
            stats["rooms_checked"] += 1
            left, conf = expected_stock(room["badge"], room["dropdown"], s.page_dropdown_cap)
            want = (
                left,
                conf,
                Decimal(room["min_price"]) if room["min_price"] is not None else None,
            )
            got = db.get(pid, {}).get(rid)
            if got == want:
                stats["rooms_match"] += 1
            else:
                problems.append(f"{slug} {stay} room {rid}: db={got} html={want}")
    print(dict(stats))
    print(f"problems: {len(problems)}")
    for p in problems[:30]:
        print("  ", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(int(sys.argv[1]))))
