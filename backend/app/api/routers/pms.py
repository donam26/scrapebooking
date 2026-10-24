from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import SessionDep, TenantDep, WriterDep, ensure_hotel_in_tenant
from app.api.schemas import ORM
from app.db.models import (
    OwnHotelDaily,
    PmsColumnMapping,
    PmsImport,
    Tenant,
    TenantHotel,
    User,
)
from app.market.pace_report import tenant_today
from app.pms.base import ADAPTERS, CANONICAL_COLUMNS, ImportSummary, PmsAdapterError
from app.pms.csv_adapter import CsvAdapter, template_csv
from app.pms.otb import (
    parse_bookings,
    parse_otb_report,
    suggest_booking_mapping,
    suggest_otb_mapping,
)

router = APIRouter(prefix="/pms", tags=["pms"])


class MappingOut(BaseModel):
    adapter: str
    mapping: dict[str, str]
    canonical_columns: list[str]


class MappingIn(BaseModel):
    adapter: str = "csv"
    mapping: dict[str, str]


# Loại tệp PMS (UX Phase 3, C4): công suất theo ngày (/pms/import), phòng đã đặt theo ngày hoặc
# danh sách đặt phòng (/pms/otb/import).
PmsFileKind = Literal["daily", "otb_report", "bookings"]
# Cột bắt buộc theo loại: thiếu thì không nhập được (OTB và đặt phòng không có ánh xạ tay).
REQUIRED: dict[str, tuple[str, ...]] = {
    "daily": ("stay_date",),
    "otb_report": ("stay_date", "rooms_otb"),
    "bookings": ("arrival", "departure", "booking_date"),
}


def detect_kind(columns: list[str]) -> PmsFileKind:
    """Nhận loại tệp theo tên cột: có ngày đến + ngày đi = danh sách đặt phòng; có ngày chụp hoặc
    cột "phòng đã đặt" riêng (không phải cột của báo cáo công suất) = phòng đã đặt theo ngày; còn
    lại = báo cáo công suất theo ngày."""
    booking = suggest_booking_mapping(columns)
    if "arrival" in booking and "departure" in booking:
        return "bookings"
    otb = suggest_otb_mapping(columns)
    daily = CsvAdapter().suggest_mapping(columns)
    if "as_of_date" in otb:
        return "otb_report"
    if (
        "rooms_otb" in otb
        and otb["rooms_otb"] not in daily.values()
        and "occupancy_pct" not in daily
    ):
        return "otb_report"
    return "daily"


class PreviewOut(BaseModel):
    columns: list[str]
    sample: list[dict[str, Any]]
    suggested_mapping: dict[str, str]
    parsed_ok: int
    errors: list[dict[str, Any]]
    # Loại tệp dùng cho xem trước (đã chọn hoặc tự nhận) và loại tự nhận theo cột.
    kind: PmsFileKind = "daily"
    detected_kind: PmsFileKind = "daily"
    # Cột bắt buộc của loại này chưa tìm thấy trong tệp.
    missing: list[str] = []


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
    # Ai nhập (null: nhập trước migration 0021 hoặc tài khoản đã xoá).
    created_by_email: str | None = None
    # Chỉ có ngay sau khi nhập: đêm đầu và cuối đã nhập (để báo "đã có trên Lịch giá & phòng").
    stay_from: date | None = None
    stay_to: date | None = None


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


@router.post("/preview", response_model=PreviewOut)
async def preview(
    tenant_id: TenantDep,
    _: WriterDep,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    adapter: Annotated[str, Form()] = "csv",
    kind: Annotated[PmsFileKind | None, Form()] = None,
) -> PreviewOut:
    """Đọc tệp, tự nhận loại (công suất / phòng đã đặt / danh sách đặt phòng) theo cột, rồi đọc thử
    theo loại `kind` (người dùng đổi) hoặc loại tự nhận. Không ghi gì."""
    ad = _adapter(adapter)
    content = await file.read()
    try:
        table = ad.read_table(content, file.filename or "upload")
    except PmsAdapterError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    detected = detect_kind(table.columns)
    use = kind or detected
    ok: int
    if use == "daily":
        mapping = effective_mapping(
            await _mapping(session, tenant_id, adapter),
            ad.suggest_mapping(table.columns),
            table.columns,
        )
        rows, errors = ad.parse(table, mapping)
        ok = len(rows)
    elif use == "otb_report":
        tenant = await session.get(Tenant, tenant_id)
        today = tenant_today(tenant) if tenant else date.today()
        mapping = suggest_otb_mapping(table.columns)
        otb_rows, errors = parse_otb_report(table, mapping, today)
        ok = len(otb_rows)
    else:
        mapping = suggest_booking_mapping(table.columns)
        bookings, errors = parse_bookings(table, mapping)
        ok = len(bookings)
    return PreviewOut(
        columns=table.columns,
        sample=table.rows[:10],
        suggested_mapping=mapping,
        parsed_ok=ok,
        errors=[e.__dict__ for e in errors[:50]],
        kind=use,
        detected_kind=detected,
        missing=[c for c in REQUIRED[use] if c not in mapping],
    )


@router.post("/import", response_model=PmsImportOut, status_code=status.HTTP_201_CREATED)
async def import_file(
    tenant_id: TenantDep,
    principal: WriterDep,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    hotel_id: Annotated[int, Form()],
    adapter: Annotated[str, Form()] = "csv",
) -> PmsImportOut:
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
    content = await file.read()
    filename = file.filename or "upload"
    try:
        table = ad.read_table(content, filename)
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
        errors=[e.__dict__ for e in errors],
        status=summary.status,
        created_by=principal.user_id,
    )
    session.add(record)
    await session.commit()
    out = PmsImportOut.model_validate(record)
    out.created_by_email = principal.email
    if rows:
        out.stay_from = min(r.stay_date for r in rows)
        out.stay_to = max(r.stay_date for r in rows)
    return out


@router.get("/imports", response_model=list[PmsImportOut])
async def list_imports(
    tenant_id: TenantDep, session: SessionDep, limit: int = Query(20, ge=1, le=200)
) -> list[PmsImportOut]:
    rows = await session.execute(
        select(PmsImport, User.email)
        .outerjoin(User, User.id == PmsImport.created_by)
        .where(PmsImport.tenant_id == tenant_id)
        .order_by(PmsImport.id.desc())
        .limit(limit)
    )
    out: list[PmsImportOut] = []
    for record, email in rows.all():
        item = PmsImportOut.model_validate(record)
        item.created_by_email = email
        out.append(item)
    return out


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
