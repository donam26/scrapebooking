"""Tạo đợt quét thủ công (tenant hoặc toàn hệ thống), một run mỗi kênh, và đẩy job vào hàng đợi."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ApiQueue
from app.db.models import ScanRun
from app.repo.runs import ScanRunRepository
from app.scheduler.planning import build_hotel_plans, channel_trigger_key, rows_by_channel
from app.scheduler.service import load_watch_rows

DEDUP_WINDOW = timedelta(minutes=10)


async def create_manual_run(
    session: AsyncSession,
    queue: ApiQueue | None,
    tenant_id: int | None,
    hotel_id: int | None = None,
) -> list[ScanRun]:
    """Đợt quét thủ công cho một tenant (tenant_id) hoặc mọi tenant đang hoạt động (None): một run
    cho mỗi kênh có listing đang quét. `hotel_id`: chỉ quét một khách sạn của tenant đó.

    Trong 10 phút, gọi lại trả về run đang chạy của kênh đó thay vì tạo thêm (tránh quét trùng).
    """
    if queue is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "job queue unavailable")
    now = datetime.now(tz=UTC)
    prefix = f"manual:t{tenant_id}:" if tenant_id is not None else "manual:all:"
    if hotel_id is not None:
        prefix += f"h{hotel_id}:"
    rows = await load_watch_rows(session, (tenant_id,) if tenant_id is not None else None)
    if hotel_id is not None:
        rows = [r for r in rows if r.hotel_id == hotel_id]
        if not rows:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "hotel has no active listing")
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "watchlist is empty")
    repo = ScanRunRepository(session)
    runs: list[ScanRun] = []
    created: list[tuple[ScanRun, list[int], str]] = []
    for channel, channel_rows in rows_by_channel(rows).items():
        recent = (
            await session.execute(
                select(ScanRun)
                .where(
                    ScanRun.trigger_key.like(prefix + "%"),
                    # Lượt quét cả watchlist không coi lượt quét một khách sạn là trùng.
                    ~ScanRun.trigger_key.like(prefix + "h%") if hotel_id is None else true(),
                    ScanRun.channel == channel,
                    # Đang chạy (bất kể bao lâu) hoặc vừa tạo trong 10 phút: không tạo thêm.
                    or_(ScanRun.status == "running", ScanRun.scheduled_at >= now - DEDUP_WINDOW),
                )
                .order_by(ScanRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if recent is not None:
            runs.append(recent)
            continue
        plans = build_hotel_plans(channel_rows, now)
        key = channel_trigger_key(f"{prefix}{now:%Y%m%dT%H%M%S}", channel)
        run = await repo.create_run(key, now, plans, channel)
        if run is None:  # trùng khoá trong cùng giây
            raise HTTPException(status.HTTP_409_CONFLICT, "scan run already created")
        runs.append(run)
        created.append((run, [p.hotel_id for p in plans], channel))
    await session.commit()
    for run, hotel_ids, channel in created:
        for hotel_id in hotel_ids:
            await queue.enqueue_probe(run.id, hotel_id, channel)
    return runs
