"""scripts/seed_demo.py phải chạy được trên schema hiện tại (README hướng dẫn chạy nó đầu tiên)."""

import importlib.util
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import HotelDateMetric, Listing, ScanRun, Tenant, User

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "seed_demo.py"


def _load_seed_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_seed_demo_creates_tenant_listings_runs_and_metrics(
    db: AsyncSession, settings: Settings
) -> None:
    seed_demo = _load_seed_module()
    result = await seed_demo.seed(db, settings)
    assert result["skipped"] is False
    assert len(result["hotel_ids"]) == 3 and len(result["run_ids"]) == 6

    tenant = (
        await db.execute(select(Tenant).where(Tenant.name == seed_demo.TENANT_NAME))
    ).scalar_one()
    assert tenant.reference_channel == "booking"
    listings = (
        (await db.execute(select(Listing).where(Listing.channel == "booking"))).scalars().all()
    )
    assert {listing.status for listing in listings} == {"active"} and len(listings) == 3
    users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    assert users == 3
    runs = (await db.execute(select(ScanRun.status))).scalars().all()
    assert len(runs) == 6 and set(runs) == {"completed"}
    metrics = (await db.execute(select(func.count()).select_from(HotelDateMetric))).scalar_one()
    assert metrics > 0

    # Chạy lần hai không nhân đôi dữ liệu.
    again = await seed_demo.seed(db, settings)
    assert again == {"skipped": True}
