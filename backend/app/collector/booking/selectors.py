import re
from datetime import date

# 4: đối chiếu HTML thật 2026-09 (ô loại phòng <th>, "We have N left", giờ chót, Booking Basic)
PARSER_VERSION = "4"

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


# Ngày check-in mà trang hiển thị (<input name="checkin" value="…">, thứ tự thuộc tính tuỳ ý).
# Booking nghi bot thì 301 về URL trần: trang vẫn 200 nhưng checkin rỗng và không có bảng giá.
_CHECKIN_TAG_RE = re.compile(r"""<input\b[^>]*\bname=["']checkin["'][^>]*>""", re.IGNORECASE)
_VALUE_ATTR_RE = re.compile(r"""\bvalue=["']([^"']*)["']""")


def page_checkin(html: str) -> str | None:
    """Giá trị checkin trên trang; "" nếu ô rỗng; None nếu trang không có ô checkin."""
    tag = _CHECKIN_TAG_RE.search(html)
    if tag is None:
        return None
    value = _VALUE_ATTR_RE.search(tag.group(0))
    return value.group(1) if value else ""


def dates_dropped(html: str) -> bool:
    """Chặn mềm: Booking bỏ tham số tìm kiếm (ô checkin rỗng)."""
    return page_checkin(html) == ""


def shown_other_checkin(html: str, checkin: date) -> str | None:
    """Ngày check-in khác ngày đã yêu cầu mà trang hiển thị (không phải chặn); None nếu khớp."""
    shown = page_checkin(html)
    return shown if shown and shown != checkin.isoformat() else None


# ---- Bảng phòng ----
ROOM_TABLE = "#hprt-table"
ROOM_ROWS = "#hprt-table tr[data-block-id]"
ROOM_TYPE_CELL = ".hprt-table-cell-roomtype"  # <th rowspan=…> ở dòng đầu của mỗi loại phòng
ROOM_NAME_LINK = "a.hprt-roomtype-link"  # có data-room-id
ROOM_NAME_TEXT = "span.hprt-roomtype-icon-link"
OCCUPANCY_CELL = "td.hprt-table-cell-occupancy"
# Nhận phòng trong ngày: không có cột trên, sức chứa ghi "Sleeps: 2 adults" trong ô loại phòng.
ROOMTYPE_OCCUPANCY = ".hprt-roomtype-occupancy-info"
SLEEPS_ADULTS_RE = re.compile(r"(\d+)\s*adults?", re.IGNORECASE)
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
# "Booking Basic": giá đối tác bán lại ("Partner offer", data-block-id "bbasic_0" hoặc
# "<room_id>_bbasic_0", không có dropdown). Không phải giá/tồn kho của chính khách sạn.
PARTNER_BLOCK_MARKER = "bbasic"

# ---- Trang ----
# Trang thật: <div id="no_availability_msg"> "We have no availability here between …".
SOLD_OUT_MARKERS = (
    "#no_availability_msg, #no_availability_message, .hprt-no-rooms-available, "
    "[data-testid='property-sold-out']"
)
# Theo thứ tự ưu tiên: tiêu đề gọn trước, #hp_hotel_name (khối lớn) cuối cùng.
HOTEL_NAME_PRIORITY = (
    "[data-testid='property-page-title']",
    "h2.pp-header__title",
    "#hp_hotel_name",
)
HOTEL_NAME = ", ".join(HOTEL_NAME_PRIORITY)

# "We have 2 left" (trang thật 2026-09) và "Only 2 rooms left on our site" (dạng cũ).
ONLY_X_LEFT_RE = re.compile(r"(?:only|we have)\s+(\d+)\s+(?:rooms?\s+)?left", re.IGNORECASE)
HOTEL_ID_RE = re.compile(r"""b_hotel_id\s*[:=]\s*['"]?(\d+)""")
MAX_PEOPLE_RE = re.compile(r"(\d+)")
