"""Đối chiếu thang tìm kiếm của thị trường với thang lịch của từng khách sạn.

Thang tìm kiếm (app/marketscan): khách sạn còn bán được ≥ N phòng cùng lúc (`nbRooms = N`, 1 người
lớn/phòng, N ≤ 30) → `market_list_prices.rooms_min` → khoảng [N, nấc kế − 1]; khách sạn của khu
vực vắng mặt đêm đó = hết phòng theo tìm kiếm. Thang lịch
(worker/capacity_ladder.py): `hotel_calendars.rooms_min/rooms_max` (tới 100) của run quét thường gần
nhất cùng đêm. Hai khoảng phải giao nhau; lệch nghĩa là hai truy vấn của Booking trả lời khác nhau
(khác số người lớn, loại phòng, thời điểm quét…) và thang tìm kiếm chưa thay được quét chi tiết.

Dùng: cd backend && uv run python scripts/validate_market_ladder.py <area_id> [số đêm, mặc định 14]
"""

import asyncio
import sys
from collections import Counter
from datetime import date

from sqlalchemy import text

from app.config import get_settings
from app.db.engine import make_engine
from app.marketscan.ladder import hotel_range

QUERY = text(
    """
    WITH scans AS (
      SELECT DISTINCT ON (stay_date) id, stay_date
      FROM market_list_scans
      WHERE area_id = :area AND enumerated AND stay_date >= current_date
        AND hotels_seen >= 0.98 * properties_found  -- vắng mặt = hết phòng chỉ khi danh sách đủ
      ORDER BY stay_date, scanned_at DESC
      LIMIT :nights
    ),
    cal AS (
      SELECT DISTINCT ON (c.hotel_id, c.stay_date)
             c.hotel_id, c.stay_date, c.available, c.rooms_min, c.rooms_max, c.fetched_at
      FROM hotel_calendars c
      JOIN scans s ON s.stay_date = c.stay_date
      ORDER BY c.hotel_id, c.stay_date, c.fetched_at DESC
    )
    SELECT s.stay_date, h.id, h.name, p.rooms_min AS search_min,
           cal.available, cal.rooms_min AS cal_min, cal.rooms_max AS cal_max,
           m.rooms_left_min AS page_min, m.rooms_left_max AS page_max
    FROM scans s
    JOIN cal ON cal.stay_date = s.stay_date
    JOIN market_area_hotels ah ON ah.area_id = :area AND ah.hotel_id = cal.hotel_id
    JOIN hotels h ON h.id = cal.hotel_id
    LEFT JOIN market_list_prices p ON p.scan_id = s.id AND p.hotel_id = cal.hotel_id
    LEFT JOIN hotel_date_metrics m
      ON m.hotel_id = cal.hotel_id AND m.stay_date = s.stay_date AND m.channel = 'booking'
    ORDER BY h.name, s.stay_date
    """
)


def _overlap(a: tuple[int, int | None], b: tuple[int, int | None]) -> bool:
    highs = [x for x in (a[1], b[1]) if x is not None]
    return not highs or max(a[0], b[0]) <= min(highs)


def _fmt(lo: int | None, hi: int | None) -> str:
    if lo is None and hi is None:
        return "—"
    if hi is None:
        return f"≥{lo}"
    return str(lo) if lo == hi else f"{lo}–{hi}"


async def main(area_id: int, nights: int) -> None:
    settings = get_settings()
    rungs = settings.market_rungs
    engine = make_engine(settings.database_url)
    async with engine.connect() as conn:
        rows = (await conn.execute(QUERY, {"area": area_id, "nights": nights})).all()
    await engine.dispose()
    verdicts: Counter[str] = Counter()
    print(f"{'khách sạn':<36} {'đêm':<10} {'tìm kiếm':>9} {'lịch':>9} {'trang':>9}  kết luận")
    for night, _hid, name, search_min, available, cal_min, cal_max, page_min, page_max in rows:
        lo, hi = hotel_range(search_min, rungs)
        search = (lo, hi) if lo is not None else (0, 0)
        cal_lo = cal_min if cal_min is not None else (1 if available else 0)
        cal = (cal_lo, cal_max if cal_max is not None else (None if available else 0))
        if not available and cal_min is None:
            verdict = "khớp (hết)" if search == (0, 0) else "LỆCH: lịch hết, tìm kiếm còn"
        else:
            verdict = "khớp" if _overlap(search, cal) else "LỆCH"
        verdicts[verdict.split(":")[0]] += 1
        night_s = night.isoformat() if isinstance(night, date) else str(night)
        print(
            f"{(name or '?')[:36]:<36} {night_s:<10} {_fmt(*search):>9} {_fmt(*cal):>9} "
            f"{_fmt(page_min, page_max):>9}  {verdict}"
        )
    total = sum(verdicts.values())
    print(f"\n{total} cặp (khách sạn, đêm): " + ", ".join(f"{k} {v}" for k, v in verdicts.items()))


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 14))
