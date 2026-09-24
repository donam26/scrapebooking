"""Interface PmsAdapter (spec mục 10).

`parse(source) -> list[OwnHotelDailyRow]` và `validate(rows) -> list[RowError]`, gom thành
`parse(table, mapping) -> (rows, errors)` để giao diện hiển thị lỗi từng dòng.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

CANONICAL_COLUMNS = (
    "stay_date",
    "rooms_total",
    "rooms_sold",
    "rooms_available",
    "occupancy_pct",
    "adr",
    "revenue",
)
REQUIRED_COLUMNS = ("stay_date",)
ADAPTERS = ("csv",)


class PmsAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class OwnHotelDailyRow:
    stay_date: date
    rooms_total: int | None
    rooms_sold: int | None
    rooms_available: int | None
    occupancy_pct: Decimal | None
    adr: Decimal | None
    revenue: Decimal | None


@dataclass(frozen=True)
class RowError:
    row: int  # số dòng trong file (1-based, không tính header)
    column: str | None
    message: str


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[dict[str, Any]]


@dataclass
class ImportSummary:
    row_count: int
    ok_count: int
    errors: list[RowError] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.ok_count == 0 and self.row_count > 0:
            return "failed"
        if self.errors:
            return "partial"
        return "completed"


class PmsAdapter(Protocol):
    name: str

    def read_table(self, content: bytes, filename: str) -> Table: ...

    def suggest_mapping(self, columns: list[str]) -> dict[str, str]: ...

    def parse(
        self, table: Table, mapping: dict[str, str]
    ) -> tuple[list[OwnHotelDailyRow], list[RowError]]: ...
