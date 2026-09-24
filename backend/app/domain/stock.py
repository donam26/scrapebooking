from dataclasses import dataclass

from app.domain.models import StockConfidence


@dataclass(frozen=True)
class Stock:
    rooms_left: int | None
    confidence: StockConfidence


def derive_stock(badge_count: int | None, dropdown_max: int | None, page_cap: int) -> Stock:
    """Suy ra số phòng còn và mức tin cậy từ hai tín hiệu thô trên trang.

    - badge_count: số trong "Only X rooms left", None nếu không có badge.
    - dropdown_max: giá trị lớn nhất của dropdown chọn số phòng, None nếu không có.
    - page_cap: trần của dropdown trên trang (cấu hình PAGE_DROPDOWN_CAP).
    """
    if badge_count is not None:
        if badge_count == 0:
            return Stock(0, StockConfidence.SOLD_OUT)
        return Stock(badge_count, StockConfidence.EXACT)
    if dropdown_max is None:
        return Stock(None, StockConfidence.HIDDEN)
    if dropdown_max == 0:
        return Stock(0, StockConfidence.SOLD_OUT)
    if dropdown_max >= page_cap:
        return Stock(dropdown_max, StockConfidence.CAPPED)
    return Stock(None, StockConfidence.HIDDEN)
