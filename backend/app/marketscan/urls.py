"""URL trang kết quả tìm kiếm Booking.com cho một khu vực (thuần).

Trang SSR chỉ trả trang đầu (20–25 thẻ; `offset` bị bỏ qua), nên muốn thấy nhiều khách sạn hơn phải
đổi "lát": bộ lọc `nflt` (hạng sao, loại chỗ ở, điểm đánh giá, khu phố…) và thứ tự `order`.
"""

from datetime import date, timedelta
from urllib.parse import urlencode

SEARCH_URL = "https://www.booking.com/searchresults.en-gb.html"
WARMUP_URL = "https://www.booking.com/"


def build_search_url(
    dest_id: str,
    dest_type: str,
    checkin: date,
    adults: int = 2,
    currency: str = "VND",
    order: str | None = None,
    nflt: str | None = None,
) -> str:
    """1 đêm, 1 phòng, `adults` người lớn, không trẻ em, tiền tệ cố định (không quy đổi).
    `order`: popularity (mặc định), price, price_from_high_to_low, review_score_and_price…;
    `nflt`: bộ lọc dạng "class=3;ht_id=204"."""
    params: dict[str, str | int] = {
        "dest_id": dest_id,
        "dest_type": dest_type,
        "checkin": checkin.isoformat(),
        "checkout": (checkin + timedelta(days=1)).isoformat(),
        "group_adults": adults,
        "no_rooms": 1,
        "group_children": 0,
        "selected_currency": currency,
        "lang": "en-gb",
    }
    if nflt:
        params["nflt"] = nflt
    if order:
        params["order"] = order
    # Luôn có `offset=0` như liên kết của Booking: thiếu tham số này, phiên có thể vào chế độ cuộn
    # vô hạn (15 thẻ) hoặc bị chuyển sang trang giới thiệu địa danh.
    params["offset"] = 0
    return f"{SEARCH_URL}?{urlencode(params)}"
