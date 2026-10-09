"""Đo nhiễu sự kiện trước/sau quy tắc Phase 2 (roadmap 2.9). Chỉ đọc DB, không ghi gì.

Tính lại trên dữ liệu đã quét (room_snapshots/probes) của N ngày gần nhất, mỗi (khách sạn, đêm,
lượt quét) so với lượt có trạng thái trước đó:
- "trước": quy tắc cũ — đổi giá mức khách sạn = giá thấp nhất mọi gói đổi ≥ ngưỡng; loại phòng
  mới/mất ngay khi xuất hiện/vắng một lượt; lịch "không bán" = hết phòng.
- "sau": `app.analytics.rules.diff_events` hiện tại (cùng loại phòng + gói, lowest_rate_shift,
  vắng ≥2 lượt, trạng thái bị hạn chế).

Chạy:  cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:55432/scrapebooking \\
           uv run python scripts/measure_event_noise.py --days 10 [--markdown]
"""

import argparse
import asyncio
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.analytics.rules import (
    DateStatus,
    EventType,
    HotelDateObs,
    Thresholds,
    diff_events,
    last_observed_before,
    pct_change,
)
from app.analytics.service import AnalyticsService
from app.db.engine import make_engine, make_session_factory
from app.db.models import Probe, ScanRun

TH = Thresholds(low_stock=3, price_change_pct=Decimal("3"))


def old_events(prev: HotelDateObs, cur: HotelDateObs) -> list[str]:
    """Quy tắc trước Phase 2 (rút gọn: chỉ các loại đem đo)."""
    old_status = {DateStatus.RESTRICTED: DateStatus.SOLD_OUT}
    ps, cs = old_status.get(prev.status, prev.status), old_status.get(cur.status, cur.status)
    if ps == DateStatus.AVAILABLE and cs == DateStatus.SOLD_OUT:
        return ["sold_out"]
    if ps == DateStatus.SOLD_OUT and cs == DateStatus.AVAILABLE:
        return ["restock"]
    if ps != DateStatus.AVAILABLE or cs != DateStatus.AVAILABLE:
        return []
    out = []
    change = pct_change(prev.min_price, cur.min_price)
    if change is not None and abs(change) >= TH.price_change_pct:
        out.append("price_up" if change > 0 else "price_down")
    for rt, room in cur.rooms.items():  # mức loại phòng: giá thấp nhất mọi gói của loại phòng
        before = prev.rooms.get(rt)
        c = pct_change(before.min_price, room.min_price) if before else None
        if c is not None and abs(c) >= TH.price_change_pct:
            out.append("room_price_up" if c > 0 else "room_price_down")
    out += ["room_type_new"] * len(set(cur.rooms) - set(prev.rooms))
    out += ["room_type_gone"] * len(set(prev.rooms) - set(cur.rooms))
    return out


async def measure(days: int) -> dict[str, dict[str, Counter[str]]]:
    url = os.environ["DATABASE_URL"]
    engine = make_engine(url)
    sf = make_session_factory(engine)
    since = datetime.now(tz=UTC) - timedelta(days=days)
    before: dict[str, Counter[str]] = defaultdict(Counter)
    after: dict[str, Counter[str]] = defaultdict(Counter)
    quality: dict[str, Counter[str]] = defaultdict(Counter)
    async with sf() as s:
        runs = [
            (r.id, r.channel)
            for r in (
                await s.execute(
                    select(ScanRun)
                    .where(
                        ScanRun.status.in_(["completed", "partial"]),
                        ScanRun.finished_at >= since,
                        ScanRun.total_probes > 0,
                    )
                    .order_by(ScanRun.finished_at)
                )
            ).scalars()
        ]
        svc = AnalyticsService(s)
        for run_id, channel in runs:
            hotels = [
                h
                for (h,) in await s.execute(
                    select(Probe.hotel_id).where(Probe.scan_run_id == run_id).distinct()
                )
            ]
            for hotel_id in hotels:
                current = await svc._load_current(run_id, hotel_id)
                if not current:
                    continue
                earliest = min(o.scanned_at for o in current.values())
                history = await svc._load_history(
                    run_id, hotel_id, channel, sorted(current), earliest - timedelta(days=8)
                )
                for d, cur in current.items():
                    hist = history.get(d, [])
                    prev = last_observed_before(hist, cur.scanned_at)
                    if prev is None:
                        continue
                    prev2 = last_observed_before(hist, prev.scanned_at)
                    for et in old_events(prev, cur):
                        before[channel][et] += 1
                    seen = {rt for h in hist if h.scanned_at < cur.scanned_at for rt in h.rooms}
                    for e in diff_events(prev, cur, TH, prev2, seen):
                        et = str(e.event_type)
                        if et in ("price_up", "price_down") and e.room_type_id is not None:
                            et = f"room_{et}"
                        after[channel][et] += 1
                        if e.event_type == EventType.LOWEST_RATE_SHIFT:
                            quality[channel][f"shift:{e.reason}"] += 1
                    # Tỷ lệ đổi giá mức khách sạn "cũ" thật sự là cùng loại phòng + gói.
                    if "price_up" in old_events(prev, cur) or "price_down" in old_events(prev, cur):
                        pc, cc = prev.cheapest(), cur.cheapest()
                        same = (
                            pc is not None
                            and cc is not None
                            and (pc.room_type_id, pc.key) == (cc.room_type_id, cc.key)
                        )
                        quality[channel]["old_price_events"] += 1
                        quality[channel]["old_price_same_room_rate"] += int(same)
    await engine.dispose()
    return {"before": before, "after": after, "quality": quality}


TYPES = (
    "price_up",
    "price_down",
    "room_price_up",
    "room_price_down",
    "lowest_rate_shift",
    "room_type_new",
    "room_type_gone",
    "sold_out",
    "restricted",
    "restock",
    "min_stay_change",
    "promo_start",
    "promo_end",
)


def report(res: dict[str, dict[str, Counter[str]]], markdown: bool) -> str:
    channels = sorted(set(res["before"]) | set(res["after"]))
    lines = []
    head = "| Kênh | Loại | Trước | Sau | Đổi |"
    lines += [head, "|---|---|---:|---:|---:|"] if markdown else [head]
    for ch in channels:
        for et in TYPES:
            b, a = res["before"][ch][et], res["after"][ch][et]
            if not b and not a:
                continue
            delta = f"{(a - b) / b:+.0%}" if b else "mới"
            lines.append(f"| {ch} | {et} | {b} | {a} | {delta} |")
    lines.append("")
    lines.append(
        "| Kênh | Đổi giá mức KS (quy tắc cũ) | cùng loại phòng + gói | Lý do lowest_rate_shift |"
    )
    if markdown:
        lines.append("|---|---:|---:|---|")
    for ch in channels:
        q = res["quality"][ch]
        n, same = q["old_price_events"], q["old_price_same_room_rate"]
        share = f"{same / n:.0%}" if n else "—"
        reasons = ", ".join(f"{k[6:]}={v}" for k, v in sorted(q.items()) if k.startswith("shift:"))
        lines.append(f"| {ch} | {n} | {same} ({share}) | {reasons or '—'} |")
    rt_b = sum(res["before"][c][t] for c in channels for t in ("room_type_new", "room_type_gone"))
    rt_a = sum(res["after"][c][t] for c in channels for t in ("room_type_new", "room_type_gone"))
    lines.append("")
    if rt_b:
        lines.append(f"room_type_new/gone: {rt_b} → {rt_a} ({(rt_a - rt_b) / rt_b:+.0%})")
    pb = sum(res["before"][c][t] for c in channels for t in ("price_up", "price_down"))
    pa = sum(res["after"][c][t] for c in channels for t in ("price_up", "price_down"))
    if pb:
        lines.append(f"price_up/down mức khách sạn: {pb} → {pa} ({(pa - pb) / pb:+.0%})")
    rb = sum(res["before"][c][t] for c in channels for t in ("room_price_up", "room_price_down"))
    ra = sum(res["after"][c][t] for c in channels for t in ("room_price_up", "room_price_down"))
    if rb:
        lines.append(f"price_up/down mức loại phòng: {rb} → {ra} ({(ra - rb) / rb:+.0%})")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()
    print(report(asyncio.run(measure(args.days)), args.markdown))


if __name__ == "__main__":
    main()
