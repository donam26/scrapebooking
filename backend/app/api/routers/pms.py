from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import SessionDep, SettingsDep, TenantDep, WriterDep, ensure_hotel_in_tenant
from app.api.schemas import ORM
from app.config import Settings
from app.db.models import OwnHotelDaily, PmsColumnMapping, PmsImport, TenantHotel
from app.pms.base import ADAPTERS, CANONICAL_COLUMNS, ImportSummary, PmsAdapterError
from app.pms.csv_adapter import CsvAdapter, template_csv

router = APIRouter(prefix="/pms", tags=["pms"])


class MappingOut(BaseModel):
    adapter: str
    mapping: dict[str, str]
    canonical_columns: list[str]


class MappingIn(BaseModel):
    adapter: str = "csv"
    mapping: dict[str, str]


class PreviewOut(BaseModel):
    columns: list[str]
    sample: list[dict[str, Any]]
    suggested_mapping: dict[str, str]
    parsed_ok: int
    errors: list[dict[str, Any]]


class PmsImportOut(ORM):
    id: int
    tenant_id: int
    hotel_id: int | None
    filename: str
    adapter: str
    row_count: int
    ok_count: int
    errors: list[dict[str, Any]]
    status: str
    created_at: datetime


class OwnDailyOut(ORM):
    hotel_id: int
    stay_date: datetime | Any
    rooms_total: int | None
    rooms_sold: int | None
    rooms_available: int | None
    occupancy_pct: Any
    adr: Any
    revenue: Any
    source: str
    imported_at: datetime


def effective_mapping(
    stored: dict[str, str], suggested: dict[str, str], columns: list[str]
) -> dict[str, str]:
    """Ánh xạ đã lưu chỉ dùng cho cột có trong tệp; cột thiếu lấy theo gợi ý."""
    out: dict[str, str] = {}
    for col in CANONICAL_COLUMNS:
        src = stored.get(col)
        if src and src in columns:
            out[col] = src
        elif suggested.get(col):
            out[col] = suggested[col]
    return out


def _adapter(name: str) -> CsvAdapter:
    if name not in ADAPTERS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown adapter {name!r}")
    return CsvAdapter()


async def _mapping(session: SessionDep, tenant_id: int, adapter: str) -> dict[str, str]:
    row = (
        await session.execute(
            select(PmsColumnMapping).where(
                PmsColumnMapping.tenant_id == tenant_id, PmsColumnMapping.adapter == adapter
            )
        )
    ).scalar_one_or_none()
    return dict(row.mapping) if row else {}


@router.get("/template", response_class=PlainTextResponse)
async def template(_: TenantDep) -> str:
    return template_csv()


@router.get("/mapping", response_model=MappingOut)
async def get_mapping(
    tenant_id: TenantDep, session: SessionDep, adapter: str = "csv"
) -> MappingOut:
    _adapter(adapter)
    return MappingOut(
        adapter=adapter,
        mapping=await _mapping(session, tenant_id, adapter),
        canonical_columns=list(CANONICAL_COLUMNS),
    )


@router.put("/mapping", response_model=MappingOut)
async def put_mapping(
    body: MappingIn, tenant_id: TenantDep, _: WriterDep, session: SessionDep
) -> MappingOut:
    _adapter(body.adapter)
    unknown = [k for k in body.mapping if k not in CANONICAL_COLUMNS]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown columns {unknown}")
    stmt = (
        insert(PmsColumnMapping)
        .values(
            tenant_id=tenant_id,
            adapter=body.adapter,
            mapping=body.mapping,
            updated_at=datetime.now(tz=UTC),
        )
        .on_conflict_do_update(
            index_elements=[PmsColumnMapping.tenant_id, PmsColumnMapping.adapter],
            set_={"mapping": body.mapping, "updated_at": datetime.now(tz=UTC)},
        )
    )
    await session.execute(stmt)
    await session.commit()
    return MappingOut(
        adapter=body.adapter, mapping=body.mapping, canonical_columns=list(CANONICAL_COLUMNS)
    )


async def _read_upload(file: UploadFile, settings: Settings) -> bytes:
    """Đọc tệp tải lên có trần kích thước (413): kiểm `size` trước, rồi đọc theo khối để không
    tin vào Content-Length."""
    limit = settings.pms_max_upload_bytes
    if file.size is not None and file.size > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"file larger than {limit} bytes"
        )
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(256 * 1024):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"file larger than {limit} bytes"
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/preview", response_model=PreviewOut)
async def preview(
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    adapter: Annotated[str, Form()] = "csv",
) -> PreviewOut:
    ad = _adapter(adapter)
    content = await _read_upload(file, settings)
    try:
        table = ad.read_table(content, file.filename or "upload", max_rows=settings.pms_max_rows)
    except PmsAdapterError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    mapping = effective_mapping(
        await _mapping(session, tenant_id, adapter),
        ad.suggest_mapping(table.columns),
        table.columns,
    )
    rows, errors = ad.parse(table, mapping)
    return PreviewOut(
        columns=table.columns,
        sample=table.rows[:10],
        suggested_mapping=mapping,
        parsed_ok=len(rows),
        errors=[e.__dict__ for e in errors[:50]],
    )


@router.post("/import", response_model=PmsImportOut, status_code=status.HTTP_201_CREATED)
async def import_file(
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    hotel_id: Annotated[int, Form()],
    adapter: Annotated[str, Form()] = "csv",
) -> PmsImport:
    await ensure_hotel_in_tenant(session, tenant_id, hotel_id)
    link = (
        await session.execute(
            select(TenantHotel).where(
                TenantHotel.tenant_id == tenant_id, TenantHotel.hotel_id == hotel_id
            )
        )
    ).scalar_one()
    if link.role != "self":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "PMS data only for role=self hotel"
        )
    ad = _adapter(adapter)
    content = await _read_upload(file, settings)
    filename = file.filename or "upload"
    try:
        table = ad.read_table(content, filename, max_rows=settings.pms_max_rows)
    except PmsAdapterError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    mapping = effective_mapping(
        await _mapping(session, tenant_id, adapter),
        ad.suggest_mapping(table.columns),
        table.columns,
    )
    rows, errors = ad.parse(table, mapping)
    now = datetime.now(tz=UTC)
    for r in rows:
        values = dict(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            stay_date=r.stay_date,
            rooms_total=r.rooms_total,
            rooms_sold=r.rooms_sold,
            rooms_available=r.rooms_available,
            occupancy_pct=r.occupancy_pct,
            adr=r.adr,
            revenue=r.revenue,
            source="csv",
            imported_at=now,
        )
        stmt = (
            insert(OwnHotelDaily)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    OwnHotelDaily.tenant_id,
                    OwnHotelDaily.hotel_id,
                    OwnHotelDaily.stay_date,
                ],
                set_={
                    k: v
                    for k, v in values.items()
                    if k not in ("tenant_id", "hotel_id", "stay_date")
                },
            )
        )
        await session.execute(stmt)
    summary = ImportSummary(row_count=len(table.rows), ok_count=len(rows), errors=errors)
    record = PmsImport(
        tenant_id=tenant_id,
        hotel_id=hotel_id,
        filename=filename[:255],
        adapter=adapter,
        row_count=summary.row_count,
        ok_count=summary.ok_count,
        errors=[e.__dict__ for e in errors[: settings.pms_max_errors_stored]],
        status=summary.status,
    )
    session.add(record)
    await session.commit()
    return record


@router.get("/imports", response_model=list[PmsImportOut])
async def list_imports(
    tenant_id: TenantDep, session: SessionDep, limit: int = Query(20, ge=1, le=200)
) -> list[PmsImport]:
    return list(
        (
            await session.execute(
                select(PmsImport)
                .where(PmsImport.tenant_id == tenant_id)
                .order_by(PmsImport.id.desc())
                .limit(limit)
            )
        ).scalars()
    )


@router.get("/daily", response_model=list[OwnDailyOut])
async def own_daily(
    tenant_id: TenantDep,
    session: SessionDep,
    hotel_id: int | None = None,
    limit: int = Query(120, ge=1, le=1000),
) -> list[OwnHotelDaily]:
    stmt = select(OwnHotelDaily).where(OwnHotelDaily.tenant_id == tenant_id)
    if hotel_id is not None:
        stmt = stmt.where(OwnHotelDaily.hotel_id == hotel_id)
    stmt = stmt.order_by(OwnHotelDaily.stay_date.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())
