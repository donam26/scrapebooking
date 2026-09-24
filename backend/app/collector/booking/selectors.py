import re

PARSER_VERSION = "1"

# Trang đã sẵn sàng (đã qua challenge) khi có một trong các phần tử này.
READY_SELECTOR = (
    "#hprt-table, #hp_hotel_name, [data-testid='property-page-content'], input[name='ss']"
)

# Chấp nhận cả dạng object literal (`b_csrf_token: '...'`, `"b_csrf_token": "..."`)
# lẫn dạng gán biến (`b_csrf_token = '...'`).
_CSRF_RE = re.compile(r"""["']?b_csrf_token["']?\s*[:=]\s*["']([^"']+)["']""")


def extract_csrf_token(html: str) -> str | None:
    m = _CSRF_RE.search(html)
    return m.group(1) if m else None


# ---- Bảng phòng ----
ROOM_TABLE = "#hprt-table"
ROOM_ROWS = "#hprt-table tr[data-block-id]"
ROOM_TYPE_CELL = "td.hprt-table-cell-roomtype"  # chỉ có ở dòng đầu của mỗi loại phòng
ROOM_NAME_LINK = "a.hprt-roomtype-link"  # có data-room-id
ROOM_NAME_TEXT = "span.hprt-roomtype-icon-link"
OCCUPANCY_CELL = "td.hprt-table-cell-occupancy"
PRICE_CELL = "td.hprt-table-cell-price"
PRICE_TEXT = (
    "span.prco-valign-middle-helper, "
    "[data-testid='price-and-discounted-price'], "
    ".bui-price-display__value"
)
CONDITIONS_CELL = "td.hprt-table-cell-conditions"
ONLY_X_LEFT = (
    ".only_x_left, .hprt-table-cell-conditions .urgency_message, "
    "[data-testid='availability-scarcity']"
)
ROOM_SELECT = "select.hprt-nos-select"

# ---- Trang ----
SOLD_OUT_MARKERS = (
    "#no_availability_message, .hprt-no-rooms-available, [data-testid='property-sold-out']"
)
HOTEL_NAME = "#hp_hotel_name, h2.pp-header__title, [data-testid='property-page-title']"

ONLY_X_LEFT_RE = re.compile(r"only\s+(\d+)\s+(?:rooms?\s+)?left", re.IGNORECASE)
HOTEL_ID_RE = re.compile(r"""b_hotel_id\s*[:=]\s*['"]?(\d+)""")
MAX_PEOPLE_RE = re.compile(r"(\d+)")
