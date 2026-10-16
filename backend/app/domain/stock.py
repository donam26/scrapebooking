from dataclasses import dataclass

from app.domain.models import StockConfidence


@dataclass(frozen=True)
class Stock:
    rooms_left: int | None
    confidence: StockConfidence


def derive_stock(
    badge_count: int | None,
    dropdown_max: int | None,
    page_cap: int,
    scope: str = "room_type",
    listing_cap: int | None = None,
) -> Stock:
    """Suy ra số phòng còn và mức tin cậy từ hai tín hiệu thô trên trang.

    - badge_count: số trong "We have N left" / "Only N rooms left", None nếu không có badge.
    - dropdown_max: giá trị lớn nhất của dropdown chọn số phòng, None nếu không có.
    - page_cap: trần của dropdown trên trang (Booking: 10).
    - listing_cap: dropdown lớn nhất từng thấy ở listing này. Có khách sạn không bao giờ mở quá
      một mức thấp hơn trần trang (Park Hyatt Saigon: 9), nên mức đó cũng chỉ là "ít nhất".
    - scope: phạm vi tín hiệu (D4). "rate" ("chỉ còn 1 phòng có giá này"): loại phòng còn ít nhất
      bấy nhiêu, không phải số chính xác → capped.

    Dropdown dưới trần là số phòng còn thật: trên 19.816 quan sát Booking.com thật, badge luôn
    bằng dropdown (N = 1–7); 8–9 không có badge nhưng cùng một nguồn số liệu.
    """
    if badge_count is not None:
        if badge_count == 0:
            return Stock(0, StockConfidence.SOLD_OUT)
        if scope == "rate":
            return Stock(badge_count, StockConfidence.CAPPED)
        return Stock(badge_count, StockConfidence.EXACT)
    if dropdown_max is None:
        return Stock(None, StockConfidence.HIDDEN)
    if dropdown_max == 0:
        return Stock(0, StockConfidence.SOLD_OUT)
    cap = min(page_cap, listing_cap) if listing_cap else page_cap
    if scope == "rate" or dropdown_max >= cap:
        return Stock(dropdown_max, StockConfidence.CAPPED)
    return Stock(dropdown_max, StockConfidence.EXACT)
