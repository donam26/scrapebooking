"""Schema API thị trường khu vực (app/api/routers/market_city.py)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Phân khúc = bộ lọc Booking dạng nflt: "ht_id=204", "ht_id=204;ht_id=206;class=4"… Chỉ nhận
# các trường mô tả loại chỗ ở/chất lượng: bán kính có trường riêng (`radius_m`), còn `oos`, `price`,
# `distance` đổi nghĩa của số đếm.
_SEGMENT_FIELDS = "ht_id|class|review_score|ht_beach|hotelfacility|mealplan|fc|chaincode"
_SEGMENT_KEY = rf"(?:{_SEGMENT_FIELDS})=[0-9]{{1,10}}"
NFLT_PATTERN = rf"^{_SEGMENT_KEY}(?:;{_SEGMENT_KEY}){{0,19}}$"
Radius = Literal[1000, 3000, 5000]


class DestinationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    dest_id: str
    dest_type: str
    name: str
    label: str
    country_code: str | None
    nr_hotels: int | None
    lat: float | None
    lng: float | None


class MarketAreaConfig(BaseModel):
    list_nights: int = Field(14, ge=1, le=30)
    detail_horizon_days: int = Field(30, ge=1, le=90)
    detail_max_hotels: int = Field(300, ge=0, le=5000)
    # Trần request mỗi đêm (thị trường + danh sách + thang). detail_max_hotels/max_pages bị kẹp
    # theo MARKET_MAX_HOTELS/MARKET_MAX_PAGES phía server.
    max_pages: int = Field(60, ge=1, le=100)
    # Bán kính quanh tâm khu vực (bộ lọc `distance` của Booking); bắt buộc với `latlong`.
    radius_m: Radius | None = None
    segment_nflt: str | None = Field(None, max_length=200, pattern=NFLT_PATTERN)


class MarketAreaCreate(MarketAreaConfig):
    name: str = Field(min_length=1, max_length=200)
    # Bỏ trống với `latlong`: server đặt "lat,lng".
    dest_id: str | None = Field(None, pattern=r"^-?\d{1,30}$")
    dest_type: Literal["city", "district", "region", "landmark", "latlong"]
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    country_code: str = Field("vn", pattern=r"^[a-z]{2}$")
    channel: Literal["booking"] = "booking"

    @model_validator(mode="after")
    def _geo(self) -> Self:
        if self.dest_type == "latlong":
            if self.lat is None or self.lng is None or self.radius_m is None:
                raise ValueError("latlong area needs lat, lng and radius_m")
            self.dest_id = f"{self.lat:.5f},{self.lng:.5f}"
        else:
            if not self.dest_id:
                raise ValueError("dest_id is required")
            self.lat = self.lng = None
        return self


class MarketAreaUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    list_nights: int | None = Field(None, ge=1, le=30)
    detail_horizon_days: int | None = Field(None, ge=1, le=90)
    detail_max_hotels: int | None = Field(None, ge=0, le=5000)
    max_pages: int | None = Field(None, ge=1, le=100)
    active: bool | None = None
    # null xoá bán kính/phân khúc (khu vực `latlong` không được bỏ bán kính).
    radius_m: Radius | None = None
    segment_nflt: str | None = Field(None, max_length=200, pattern=NFLT_PATTERN)


class SelfLocationOut(BaseModel):
    """Khách sạn "của bạn" làm tâm cho khu vực bán kính."""

    hotel_id: int
    name: str | None
    lat: float
    lng: float


class MarketAreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    channel: str
    dest_id: str
    dest_type: str
    country_code: str
    lat: float | None
    lng: float | None
    radius_m: int | None
    segment_nflt: str | None
    list_nights: int
    detail_horizon_days: int
    detail_max_hotels: int
    max_pages: int
    active: bool
    list_requested_at: datetime | None
    last_list_scan_at: datetime | None
    # queued | running | completed | blocked | paused | error
    last_list_status: str | None
    last_list_error: str | None  # mã ngắn: "blocked", "error: timeout", "error: network"…
    last_detail_scan_at: datetime | None
    last_detail_run_id: int | None
    created_at: datetime
    hotels_total: int = 0


class ScanNowOut(BaseModel):
    area_id: int
    # False: đã có yêu cầu trong 10 phút hoặc vòng quét đang chạy (≤ 30 phút trước), không đẩy thêm.
    enqueued: bool
    list_requested_at: datetime | None


class PriceBucketOut(BaseModel):
    lo: Decimal
    hi: Decimal | None
    count: int


class LadderRungOut(BaseModel):
    """Nấc thang: số khách sạn còn bán được ≥ `rooms` phòng cùng lúc đêm đó (nấc 1 = danh sách)."""

    rooms: int
    available: int
    by_class: dict[str, int]  # theo hạng sao {"3": 47, …}; khách sạn chưa xếp hạng không có


class BookingHistogramOut(BaseModel):
    """Thanh "Ngân sách" của Booking: `bars` cột đều từ min tới max (VND/đêm), chiều cao tương đối
    (cột cao nhất = 100); chỗ đắt hơn max không nằm trong cột nào."""

    min: Decimal
    max: Decimal
    bars: list[int]


class CityListOut(BaseModel):
    scan_id: int | None
    status: str | None  # running | completed | capped | blocked | error
    scanned_at: datetime | None
    finished_at: datetime | None
    pages: int  # số request của đêm đó
    properties_found: int | None  # số chỗ còn phòng trong khu vực khớp phân khúc (kênh báo)
    hotels_seen: int  # khách sạn khác nhau thấy được đêm đó (giá bên dưới tính trên các KS này)
    coverage: float | None  # hotels_seen / properties_found (0–1)
    sample: bool  # True khi coverage < 98%: thống kê giá là mẫu "N/M KS"
    priced: int
    currency: str
    avg: Decimal | None
    median: Decimal | None
    p25: Decimal | None
    p75: Decimal | None
    min: Decimal | None
    max: Decimal | None
    histogram: list[PriceBucketOut]
    source: str | None = None  # graphql | ssr (dự phòng)
    autoextended: int | None = None  # chỗ Booking nới thêm ngoài khu vực (không tính ở trên)
    low_availability: bool | None = None
    # % chỗ ở của khu vực đã kín, Booking tự tính; chỉ có khi khu vực không lọc bán kính.
    unavailability_pct: int | None = None
    market_available: int | None = None  # còn phòng, mọi loại chỗ ở (không lọc phân khúc)
    segment_base: int | None = None  # mẫu số phân khúc: số còn phòng lớn nhất 30 ngày quét
    sold_out_share: float | None = None  # 1 − còn phòng / mẫu số (cận dưới)
    ladder: list[LadderRungOut] = []
    rooms_left_floor: int | None = None  # sàn tổng phòng Booking còn bán của thị trường
    tightness: float | None = None  # c(10)/c(1): thấp = căng
    tightness_median: float | None = None  # trung vị các đêm của vòng quét gần nhất
    booking_histogram: BookingHistogramOut | None = None
    composition: dict[str, int] = {}  # còn phòng theo loại chỗ ở (ht_id) của cả thị trường
    classes: dict[str, int] = {}  # còn phòng theo hạng sao của phân khúc
    enumerated: bool = False  # đã liệt kê id ở mọi nấc: khoảng phòng còn từng KS dùng được


class SelfMarketOut(BaseModel):
    """Khách sạn "của bạn" đặt cạnh thị trường đêm đó."""

    hotel_id: int
    name: str | None
    in_area: bool  # có trong kết quả khu vực đêm đó (khớp phân khúc, còn phòng)
    rank: int | None  # vị trí theo thứ tự "phổ biến" của Booking trong khu vực
    price: Decimal | None
    currency: str | None
    price_percentile: int | None  # 0–100 so giá các KS khu vực đêm đó (cao = đắt hơn)
    rooms_min: int | None  # khoảng phòng còn theo thang tìm kiếm
    rooms_max: int | None
    rooms_percentile: int | None  # 0–100: còn nhiều phòng hơn bao nhiêu % KS khu vực
    only_left: int | None
    # Từ quét trang khách sạn (chính xác hơn, tới 100 phòng): phòng còn min/max của đêm đó.
    rooms_left_min: int | None
    rooms_left_max: int | None


class CityDetailOut(BaseModel):
    hotels_with_data: int
    hotels_available: int
    hotels_sold_out: int
    rooms_left_known_sum: int
    inventory_sum: int
    occupancy_est: Decimal | None  # 1 - còn/tồn kho, chỉ trên khách sạn có ước tính đủ tin cậy
    coverage_hotels: int
    last_observed_at: datetime | None


class CityAreaOut(BaseModel):
    id: int
    name: str
    last_list_scan_at: datetime | None
    last_detail_scan_at: datetime | None
    hotels_total: int


class MarketCityOut(BaseModel):
    stay_date: date
    channel: str
    area: CityAreaOut
    list_scan: CityListOut
    detail: CityDetailOut
    self_hotel: SelfMarketOut | None = None


class MarketTrendNightOut(BaseModel):
    stay_date: date
    scanned_at: datetime | None
    status: str | None
    properties_found: int | None
    sold_out_share: float | None
    unavailability_pct: int | None
    ladder: dict[str, int]  # {"1": c(1), "10": c(10), …}
    tightness: float | None
    rooms_left_floor: int | None
    median_price: Decimal | None  # trung vị giá danh sách (VND/đêm)


class MarketTrendOut(BaseModel):
    area_id: int
    segment_base: int | None
    nights: list[MarketTrendNightOut]


class CityHotelOut(BaseModel):
    hotel_id: int
    name: str | None
    url: str | None
    image_url: str | None
    review_score: Decimal | None
    review_count: int | None
    stars: Decimal | None
    district: str | None
    distance_km: float | None  # tới khách sạn "của bạn" (cần toạ độ cả hai)
    price: Decimal | None  # giá trên danh sách đêm đó (VND, gồm thuế phí)
    currency: str | None
    available: bool | None  # None: không biết (chưa quét tới / danh sách chưa lật hết)
    rank: int | None  # hạng tốt nhất theo thứ tự mặc định của kênh ở vòng quét gần nhất
    watched: bool
    role: str | None  # self | competitor nếu đã theo dõi
    rooms_min: int | None = None  # khoảng phòng còn theo thang tìm kiếm (đêm đã liệt kê id)
    rooms_max: int | None = None  # None khi qua nấc cao nhất ("≥ rooms_min")
    only_left: int | None = None  # "We have N left at this price"


class CityHotelsOut(BaseModel):
    stay_date: date
    area_id: int
    total: int
    items: list[CityHotelOut]
