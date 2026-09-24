import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.booking.parser import parse_hotel_page
from app.collector.booking.selectors import PARSER_VERSION
from app.collector.booking.urls import currency_for
from app.collector.storage import S3RawStore
from app.config import get_settings
from app.db.engine import make_engine, make_session_factory
from app.db.models import Hotel, Probe, ScanRun, Tenant, TenantHotel
from app.db.partitions import (
    drop_room_snapshot_partitions_older_than,
    ensure_room_snapshot_partitions,
)
from app.domain.booking_url import BookingUrlError, parse_booking_url
from app.domain.models import ProbeMethod, ProbeResult, ProbeStatus
from app.logging import configure_logging
from app.repo.runs import ScanRunRepository
from app.repo.snapshots import SnapshotRepository
from app.scheduler.planning import WatchRow, build_hotel_plans
from app.scheduler.queue import ArqJobQueue

app = typer.Typer(help="Vận hành hệ thống theo dõi đối thủ khách sạn")


def _run[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    async def _inner() -> T:
        settings = get_settings()
        configure_logging(settings.log_level)
        engine = make_engine(settings.database_url)
        try:
            async with make_session_factory(engine)() as s:
                return await fn(s)
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@app.command("add-tenant")
def add_tenant(
    name: str,
    timezone: str = typer.Option("Asia/Ho_Chi_Minh", "--timezone"),
    horizon: int = typer.Option(30, "--horizon"),
    scan_times: str = typer.Option("06:00,14:00,22:00", "--scan-times"),
    country: str = typer.Option("vn", "--country"),
) -> None:
    async def _do(s: AsyncSession) -> int:
        tenant = Tenant(
            name=name,
            timezone=timezone,
            horizon_days=horizon,
            scan_times=[t.strip() for t in scan_times.split(",")],
            country_code=country,
        )
        s.add(tenant)
        await s.commit()
        return tenant.id

    typer.echo(f"tenant created id={_run(_do)}")


@app.command("add-hotel")
def add_hotel(
    tenant_id: int,
    url: str,
    role: str = typer.Option("competitor", "--role"),
    label: str | None = typer.Option(None, "--label"),
) -> None:
    try:
        ref = parse_booking_url(url)
    except BookingUrlError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    if role not in ("self", "competitor"):
        typer.echo("role must be self or competitor")
        raise typer.Exit(code=1)

    async def _do(s: AsyncSession) -> int:
        hotel = (
            await s.execute(select(Hotel).where(Hotel.booking_slug == ref.slug))
        ).scalar_one_or_none()
        if hotel is None:
            hotel = Hotel(
                booking_url=ref.canonical_url, booking_slug=ref.slug, country_code=ref.country_code
            )
            s.add(hotel)
            await s.flush()
        link = (
            await s.execute(
                select(TenantHotel).where(
                    TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel.id
                )
            )
        ).scalar_one_or_none()
        if link is None:
            s.add(
                TenantHotel(
                    tenant_id=tenant_id, hotel_id=hotel.id, role=role, label=label, active=True
                )
            )
        else:
            link.role, link.label, link.active = role, label, True
        await s.commit()
        return hotel.id

    typer.echo(f"hotel linked id={_run(_do)} slug={ref.slug}")


@app.command("add-user")
def add_user(
    email: str,
    password: str = typer.Option(..., "--password", prompt=True, hide_input=True),
    role: str = typer.Option("viewer", "--role"),
    tenant_id: int | None = typer.Option(None, "--tenant-id"),
) -> None:
    """Tạo người dùng. role: operator (không tenant), tenant_admin, viewer."""
    from app.api.auth import hash_password
    from app.db.models import User

    if role not in ("operator", "tenant_admin", "viewer"):
        typer.echo("role must be operator, tenant_admin or viewer")
        raise typer.Exit(code=1)
    if role != "operator" and tenant_id is None:
        typer.echo("--tenant-id is required for tenant roles")
        raise typer.Exit(code=1)

    async def _do(s: AsyncSession) -> int:
        user = User(
            tenant_id=None if role == "operator" else tenant_id,
            email=email.lower(),
            password_hash=hash_password(password),
            role=role,
            active=True,
        )
        s.add(user)
        await s.commit()
        return user.id

    typer.echo(f"user created id={_run(_do)}")


@app.command("scan-now")
def scan_now(enqueue: bool = typer.Option(True, "--enqueue/--no-enqueue")) -> None:
    """Tạo một scan run thủ công cho mọi tenant đang hoạt động và đẩy job vào hàng đợi."""

    async def _do(s: AsyncSession) -> tuple[int, int] | None:
        now = datetime.now(tz=UTC)
        rows = await s.execute(
            select(
                TenantHotel.tenant_id, TenantHotel.hotel_id, Tenant.horizon_days, Tenant.timezone
            )
            .join(Tenant, Tenant.id == TenantHotel.tenant_id)
            .where(TenantHotel.active.is_(True), Tenant.active.is_(True))
        )
        plans = build_hotel_plans([WatchRow(r[0], r[1], r[2], r[3]) for r in rows], now)
        if not plans:
            return None
        run = await ScanRunRepository(s).create_run(f"manual:{now:%Y%m%dT%H%M%S}", now, plans)
        if run is None:
            return None
        await s.commit()
        if enqueue:
            queue = await ArqJobQueue.connect(get_settings().redis_url)
            try:
                for p in plans:
                    await queue.enqueue_probe(run.id, p.hotel_id)
            finally:
                await queue.close()
        return run.id, len(plans)

    result = _run(_do)
    if result is None:
        typer.echo("nothing to scan")
        raise typer.Exit(code=1)
    typer.echo(f"scan run {result[0]} created with {result[1]} jobs (enqueued={enqueue})")


@app.command("ensure-partitions")
def ensure_partitions(months: int = typer.Option(3, "--months")) -> None:
    async def _do(s: AsyncSession) -> list[str]:
        conn = await s.connection()
        created = await ensure_room_snapshot_partitions(conn, datetime.now(tz=UTC).date(), months)
        await s.commit()
        return created

    typer.echo(f"created: {_run(_do)}")


@app.command("prune-partitions")
def prune_partitions(keep_months: int = typer.Option(24, "--keep-months")) -> None:
    """Xoá partition room_snapshots cũ hơn số tháng giữ lại (spec: 24 tháng)."""

    async def _do(s: AsyncSession) -> list[str]:
        conn = await s.connection()
        dropped = await drop_room_snapshot_partitions_older_than(
            conn, keep_months, datetime.now(tz=UTC).date()
        )
        await s.commit()
        return dropped

    typer.echo(f"dropped: {_run(_do)}")


@app.command("reparse")
def reparse(since_days: int = typer.Option(30, "--since-days")) -> None:
    """Parse lại HTML thô trong MinIO cho probe `ok` gần đây bằng parser hiện tại."""

    async def _do(s: AsyncSession) -> tuple[int, int]:
        settings = get_settings()
        store = S3RawStore(
            settings.minio_bucket,
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
        )
        cutoff = datetime.now(tz=UTC) - timedelta(days=since_days)
        probes = (
            await s.execute(
                select(Probe, Hotel.country_code)
                .join(Hotel, Hotel.id == Probe.hotel_id)
                .where(
                    Probe.fetched_at >= cutoff,
                    Probe.raw_object_key.is_not(None),
                    Probe.status == str(ProbeStatus.OK),
                )
                .order_by(Probe.id)
            )
        ).all()
        repo = SnapshotRepository(s, settings.page_dropdown_cap)
        done = missing = 0
        for probe, country in probes:
            assert probe.raw_object_key is not None
            html = await store.get_html(probe.raw_object_key)
            if html is None:
                missing += 1
                continue
            page = parse_hotel_page(html, currency_for(country))
            result = ProbeResult(
                status=ProbeStatus.OK if page.offers else ProbeStatus.NO_ROOMS_1N,
                method=ProbeMethod(probe.method or "http"),
                checkin=probe.checkin,
                checkout=probe.checkout,
                nights=probe.nights,
                adults=probe.adults,
                offers=page.offers,
                raw_html=None,
                http_status=probe.http_status,
                session_id=probe.session_id,
                duration_ms=probe.duration_ms,
                booking_hotel_id=page.booking_hotel_id,
                hotel_name=page.hotel_name,
            )
            await repo.write_probe(
                probe.scan_run_id,
                probe.hotel_id,
                probe.stay_date,
                result,
                probe.raw_object_key,
                PARSER_VERSION,
                probe.proxy_country,
                probe.fetched_at,
            )
            done += 1
            if done % 200 == 0:
                await s.commit()
        await s.commit()
        return done, missing

    done, missing = _run(_do)
    typer.echo(f"reparsed={done} missing_raw={missing} parser_version={PARSER_VERSION}")


@app.command("run-status")
def run_status(limit: int = typer.Option(5, "--limit")) -> None:
    async def _do(s: AsyncSession) -> list[str]:
        runs = (
            (await s.execute(select(ScanRun).order_by(ScanRun.id.desc()).limit(limit)))
            .scalars()
            .all()
        )
        return [
            f"run {r.id} {r.trigger_key} {r.status} jobs={r.total_jobs} probes={r.total_probes} "
            f"ok={r.ok_count} sold_out={r.sold_out_count} blocked={r.blocked_count} "
            f"error={r.error_count}"
            for r in runs
        ]

    for line in _run(_do):
        typer.echo(line)


@app.command("analyze")
def analyze(
    scan_run_id: int | None = typer.Option(None, "--run-id"),
    all_pending: bool = typer.Option(False, "--all-pending"),
) -> None:
    """Chạy analytics cho một scan run đã chốt (mặc định: run chốt gần nhất)."""
    from app.analytics.service import AnalyticsService

    async def _do(s: AsyncSession) -> list[str]:
        settings = get_settings()
        svc = AnalyticsService(
            s,
            low_stock_threshold=settings.low_stock_threshold,
            price_change_threshold_pct=settings.price_change_threshold_pct,
        )
        if all_pending:
            run_ids = await svc.pending_run_ids()
        elif scan_run_id is not None:
            run_ids = [scan_run_id]
        else:
            run_ids = await ScanRunRepository(s).latest_finished_run_ids(1)
        out = []
        for rid in run_ids:
            report = await svc.run(rid)
            await s.commit()
            out.append(
                f"run {rid}: hotel_dates={report.hotel_dates} events={report.events} "
                f"metrics={report.metrics}"
            )
        return out or ["nothing to analyze"]

    for line in _run(_do):
        typer.echo(line)


@app.command("insight")
def insight(tenant_id: int, sync: bool = typer.Option(True, "--sync/--batch")) -> None:
    """Sinh insight cho một tenant ngay (gọi đồng bộ) hoặc qua Batch API."""
    from app.insight.service import InsightService, build_openai_client

    async def _do(s: AsyncSession) -> str:
        settings = get_settings()
        svc = InsightService(s, client=build_openai_client(settings), settings=settings)
        row = await svc.generate(tenant_id, trigger="on_demand", use_batch=not sync)
        await s.commit()
        return f"insight {row.id} status={row.status} model={row.model} cost=${row.cost_usd}"

    typer.echo(_run(_do))


@app.command("backup-db")
def backup_db() -> None:
    """pg_dump toàn bộ DB, nén gzip, tải lên MinIO, giữ BACKUP_KEEP bản gần nhất."""
    from app.ops.backup import run_backup

    settings = get_settings()
    key, deleted = asyncio.run(run_backup(settings))
    typer.echo(f"uploaded {key}; deleted {len(deleted)} old backups")


if __name__ == "__main__":
    app()
