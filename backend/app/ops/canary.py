"""Canary trôi parser (roadmap 0.8): mỗi ngày so độ phủ các trường parse được của 24 giờ qua với 7
ngày trước đó, theo kênh. Kênh đổi giao diện thường không làm probe lỗi mà làm trường biến mất
(giá, số phòng còn, cờ thuế, nhãn KM): phát hiện trước khi khách thấy số sai.

Hàm thuần `compare_coverage` có test; `coverage_since` đọc DB.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Probe, RoomSnapshot
from app.domain.models import ProbeStatus

FIELDS = ("rooms", "price", "stock", "taxes", "breakfast")
MIN_PROBES = 20  # cửa sổ ít mẫu hơn thì không kết luận
DROP_RATIO = 0.7  # độ phủ hiện tại < 70% mức nền thì báo
MIN_BASELINE = 0.2  # trường hiếm khi có (VD nhãn KM) không đem báo


@dataclass(frozen=True)
class Coverage:
    channel: str
    ok_probes: int
    # Tỷ lệ 0..1: probe "ok" có ≥1 loại phòng; loại phòng có giá; có tín hiệu tồn phòng
    # (exact/capped); có cờ thuế rõ; có cờ bữa sáng rõ.
    shares: dict[str, float]


def compare_coverage(current: Coverage, baseline: Coverage) -> list[str]:
    """Các trường tụt độ phủ (mã trường), cần đủ mẫu ở cả hai cửa sổ."""
    if current.ok_probes < MIN_PROBES or baseline.ok_probes < MIN_PROBES:
        return []
    out = []
    for f in FIELDS:
        base = baseline.shares.get(f, 0.0)
        cur = current.shares.get(f, 0.0)
        if base >= MIN_BASELINE and cur < base * DROP_RATIO:
            out.append(f)
    return out


def canary_alert(channel: str, fields: list[str], cur: Coverage, base: Coverage) -> str | None:
    if not fields:
        return None
    parts = [f"{f} {cur.shares.get(f, 0):.0%} (was {base.shares.get(f, 0):.0%})" for f in fields]
    return (
        f"⚠️ [{channel}] parser drift: field coverage dropped — "
        + ", ".join(parts)
        + f"; {cur.ok_probes} ok probes in 24h. Check selectors/fixtures (docs/operations.md)."
    )


async def coverage_since(s: AsyncSession, start: datetime, end: datetime) -> dict[str, Coverage]:
    ok = (
        select(Probe.channel, func.count())
        .where(
            Probe.fetched_at >= start,
            Probe.fetched_at < end,
            Probe.status == str(ProbeStatus.OK),
        )
        .group_by(Probe.channel)
    )
    probes = {ch: n for ch, n in await s.execute(ok)}
    with_rooms = {
        ch: n
        for ch, n in await s.execute(
            select(RoomSnapshot.channel, func.count(func.distinct(RoomSnapshot.probe_id)))
            .where(RoomSnapshot.scanned_at >= start, RoomSnapshot.scanned_at < end)
            .group_by(RoomSnapshot.channel)
        )
    }
    first_rate = RoomSnapshot.rates[0]
    rows = await s.execute(
        select(
            RoomSnapshot.channel,
            func.count(),
            func.sum(cast(RoomSnapshot.min_price.is_not(None), Integer)),
            func.sum(cast(RoomSnapshot.stock_confidence.in_(["exact", "capped"]), Integer)),
            func.sum(cast(first_rate["taxes_included"].astext.in_(["true", "false"]), Integer)),
            func.sum(cast(first_rate["breakfast"].astext.in_(["true", "false"]), Integer)),
        )
        .where(RoomSnapshot.scanned_at >= start, RoomSnapshot.scanned_at < end)
        .group_by(RoomSnapshot.channel)
    )
    out: dict[str, Coverage] = {}
    snaps = {r[0]: r[1:] for r in rows}
    for ch, n_ok in probes.items():
        total, priced, stock, taxes, breakfast = snaps.get(ch, (0, 0, 0, 0, 0))
        total = total or 0

        def share(x: int | None, d: int) -> float:
            return float(x or 0) / d if d else 0.0

        out[ch] = Coverage(
            ch,
            n_ok,
            {
                "rooms": share(with_rooms.get(ch, 0), n_ok),
                "price": share(priced, total),
                "stock": share(stock, total),
                "taxes": share(taxes, total),
                "breakfast": share(breakfast, total),
            },
        )
    return out


async def run_canary(s: AsyncSession, now: datetime) -> list[str]:
    """Câu cảnh báo cho mọi kênh có trường tụt độ phủ (24h qua so với 7 ngày trước đó)."""
    cur = await coverage_since(s, now - timedelta(hours=24), now)
    base = await coverage_since(s, now - timedelta(days=8), now - timedelta(hours=24))
    alerts = []
    for ch, c in sorted(cur.items()):
        b = base.get(ch)
        if b is None:
            continue
        msg = canary_alert(ch, compare_coverage(c, b), c, b)
        if msg:
            alerts.append(msg)
    return alerts
