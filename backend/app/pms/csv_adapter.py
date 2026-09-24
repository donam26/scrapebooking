import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.pms.base import (
    CANONICAL_COLUMNS,
    REQUIRED_COLUMNS,
    OwnHotelDailyRow,
    PmsAdapterError,
    RowError,
    Table,
)

# Tên cột thường gặp trong file xuất từ ezCloud, Newway, Hotel Link, Smile và Excel tự làm.
_ALIASES: dict[str, tuple[str, ...]] = {
    "stay_date": ("stay_date", "date", "ngay", "ngày", "business date", "stay date", "ngày ở"),
    "rooms_total": ("rooms_total", "total rooms", "tong phong", "tổng phòng", "capacity", "rooms"),
    "rooms_sold": (
        "rooms_sold",
        "sold",
        "rooms sold",
        "occupied",
        "phong ban",
        "phòng bán",
        "phòng đã bán",
        "room nights",
    ),
    "rooms_available": (
        "rooms_available",
        "available",
        "rooms available",
        "phong trong",
        "phòng trống",
        "vacant",
    ),
    "occupancy_pct": (
        "occupancy_pct",
        "occupancy",
        "occ",
        "occ %",
        "occupancy %",
        "cong suat",
        "công suất",
    ),
    "adr": ("adr", "average daily rate", "gia trung binh", "giá trung bình", "avg rate"),
    "revenue": ("revenue", "room revenue", "doanh thu", "doanh thu phòng"),
}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%m/%d/%Y")


def _get(raw: dict[str, Any], mapping: dict[str, str], col: str) -> Any:
    src = mapping.get(col)
    return raw.get(src) if src else None


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower().replace("_", " "))


def template_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CANONICAL_COLUMNS)
    w.writerow(["2026-10-01", "120", "96", "24", "80.0", "1850000", "177600000"])
    w.writerow(["2026-10-02", "120", "108", "12", "90.0", "1990000", "214920000"])
    return buf.getvalue()


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {text!r}")


def parse_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    d = Decimal(text)
    if d != d.to_integral_value():
        raise ValueError(f"not an integer {value!r}")
    return int(d)


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace(" ", "").replace("%", "")
    if "," in text and "." in text:
        text = (
            text.replace(",", "")
            if text.rfind(".") > text.rfind(",")
            else text.replace(".", "").replace(",", ".")
        )
    elif "," in text:
        parts = text.split(",")
        text = (
            text.replace(",", "") if all(len(p) == 3 for p in parts[1:]) else text.replace(",", ".")
        )
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"not a number {value!r}") from exc


class CsvAdapter:
    """Đọc CSV hoặc Excel theo template, có ánh xạ cột."""

    name = "csv"

    def read_table(self, content: bytes, filename: str) -> Table:
        lower = filename.lower()
        if lower.endswith((".xlsx", ".xlsm")):
            return self._read_excel(content)
        return self._read_csv(content)

    @staticmethod
    def _read_csv(content: bytes) -> Table:
        for enc in ("utf-8-sig", "utf-16", "cp1258", "latin-1"):
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise PmsAdapterError("cannot decode file")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        columns = [c.strip() for c in (reader.fieldnames or []) if c is not None]
        if not columns:
            raise PmsAdapterError("empty file or missing header row")
        rows = [
            {
                k.strip(): (v.strip() if isinstance(v, str) else v)
                for k, v in r.items()
                if k is not None
            }
            for r in reader
        ]
        return Table(columns=columns, rows=rows)

    @staticmethod
    def _read_excel(content: bytes) -> Table:
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise PmsAdapterError(f"cannot read excel: {exc}") from exc
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        if not header:
            raise PmsAdapterError("empty sheet")
        columns = [str(c).strip() if c is not None else f"col{i}" for i, c in enumerate(header)]
        rows = []
        for raw in it:
            if raw is None or all(v is None for v in raw):
                continue
            rows.append({columns[i]: raw[i] for i in range(min(len(columns), len(raw)))})
        return Table(columns=columns, rows=rows)

    def suggest_mapping(self, columns: list[str]) -> dict[str, str]:
        normalised = {_norm(c): c for c in columns}
        mapping: dict[str, str] = {}
        for canonical, aliases in _ALIASES.items():
            for alias in aliases:
                if _norm(alias) in normalised:
                    mapping[canonical] = normalised[_norm(alias)]
                    break
        return mapping

    def parse(
        self, table: Table, mapping: dict[str, str]
    ) -> tuple[list[OwnHotelDailyRow], list[RowError]]:
        errors: list[RowError] = []
        for required in REQUIRED_COLUMNS:
            if required not in mapping or mapping[required] not in table.columns:
                errors.append(RowError(0, required, f"missing mapping for {required}"))
        if errors:
            return [], errors
        rows: list[OwnHotelDailyRow] = []
        seen: set[date] = set()
        for i, raw in enumerate(table.rows, start=1):
            row_errors: list[RowError] = []

            try:
                stay = parse_date(_get(raw, mapping, "stay_date"))
            except ValueError as exc:
                errors.append(RowError(i, "stay_date", str(exc)))
                continue
            if stay in seen:
                errors.append(RowError(i, "stay_date", f"duplicate date {stay.isoformat()}"))
                continue
            vals: dict[str, Any] = {}
            for col, fn in (
                ("rooms_total", parse_int),
                ("rooms_sold", parse_int),
                ("rooms_available", parse_int),
                ("occupancy_pct", parse_decimal),
                ("adr", parse_decimal),
                ("revenue", parse_decimal),
            ):
                try:
                    vals[col] = fn(_get(raw, mapping, col))
                except (ValueError, InvalidOperation) as exc:
                    row_errors.append(RowError(i, col, str(exc)))
                    vals[col] = None
            if row_errors:
                errors.extend(row_errors)
                continue
            total, sold, avail = vals["rooms_total"], vals["rooms_sold"], vals["rooms_available"]
            if avail is None and total is not None and sold is not None:
                avail = total - sold
            if sold is None and total is not None and avail is not None:
                sold = total - avail
            occ = vals["occupancy_pct"]
            if occ is None and total and sold is not None:
                occ = (Decimal(sold) / Decimal(total) * 100).quantize(Decimal("0.01"))
            if occ is not None and not (0 <= occ <= 100):
                errors.append(RowError(i, "occupancy_pct", f"out of range {occ}"))
                continue
            if total is not None and sold is not None and sold > total:
                errors.append(RowError(i, "rooms_sold", f"sold {sold} > total {total}"))
                continue
            seen.add(stay)
            rows.append(
                OwnHotelDailyRow(
                    stay_date=stay,
                    rooms_total=total,
                    rooms_sold=sold,
                    rooms_available=avail,
                    occupancy_pct=occ,
                    adr=vals["adr"],
                    revenue=vals["revenue"],
                )
            )
        return rows, errors
