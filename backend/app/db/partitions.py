from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


def month_range(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1)
    return start, end


def partition_name(d: date) -> str:
    return f"room_snapshots_{d:%Y_%m}"


async def ensure_room_snapshot_partitions(
    conn: AsyncConnection, first_month: date, months: int = 3
) -> list[str]:
    """Tạo partition theo tháng cho room_snapshots, bắt đầu từ tháng của first_month.
    Trả về danh sách partition vừa tạo mới."""
    created: list[str] = []
    start, end = month_range(first_month)
    for _ in range(months):
        name = partition_name(start)
        exists = await conn.execute(
            text("select 1 from pg_class where relname = :n").bindparams(n=name)
        )
        if exists.first() is None:
            await conn.execute(
                text(
                    f"CREATE TABLE {name} PARTITION OF room_snapshots "
                    f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
                )
            )
            created.append(name)
        start, end = month_range(end)
    return created


async def list_room_snapshot_partitions(conn: AsyncConnection) -> list[str]:
    rows = await conn.execute(
        text(
            "select c.relname from pg_inherits i "
            "join pg_class c on c.oid = i.inhrelid "
            "join pg_class p on p.oid = i.inhparent where p.relname='room_snapshots' "
            "order by c.relname"
        )
    )
    return [r[0] for r in rows]


async def drop_room_snapshot_partitions_older_than(
    conn: AsyncConnection, keep_months: int, today: date
) -> list[str]:
    """Xoá partition có tháng cũ hơn `keep_months` tháng so với tháng của `today`
    (spec mục 5.4: room_snapshots giữ 24 tháng)."""
    cutoff = today.replace(day=1)
    for _ in range(keep_months):
        cutoff = (cutoff - timedelta(days=1)).replace(day=1)
    dropped: list[str] = []
    for name in await list_room_snapshot_partitions(conn):
        try:
            year, month = int(name[-7:-3]), int(name[-2:])
        except ValueError:
            continue
        if date(year, month, 1) < cutoff:
            await conn.execute(text(f"DROP TABLE {name}"))
            dropped.append(name)
    return dropped
