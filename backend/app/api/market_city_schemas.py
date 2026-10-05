"""Schema API thị trường toàn thành phố (app/api/routers/market_city.py)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    # Ngân sách request của đêm khám phá (một lần mỗi ngày; các đêm khác chỉ 1 request).
    # detail_max_hotels/max_pages bị kẹp theo MARKET_MAX_HOTELS/MARKET_MAX_PAGES phía server.
    max_pages: int = Field(60, ge=1, le=100)


class MarketAreaCreate(MarketAreaConfig):
    name: str = Field(min_length=1, max_length=200)
    dest_id: str = Field(pattern=r"^-?\d{1,30}$")
    dest_type: Literal["city", "district", "region"]
    country_code: str = Field("vn", pattern=r"^[a-z]{2}$")
    channel: Literal["booking"] = "booking"


class MarketAreaUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    list_nights: int | None = Field(None, ge=1, le=30)
    detail_horizon_days: int | None = Field(None, ge=1, le=90)
    detail_max_hotels: int | None = Field(None, ge=0, le=5000)
    max_pages: int | None = Field(None, ge=1, le=100)
    active: bool | None = None


class MarketAreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    channel: str
    dest_id: str
    dest_type: str
    country_code: str
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


class CityListOut(BaseModel):
    scan_id: int | None
    status: str | None  # running | completed (đã có properties_found) | blocked | error
    scanned_at: datetime | None
    finished_at: datetime | None
    pages: int  # số request của đêm đó (đêm khám phá: nhiều lát bộ lọc × thứ tự)
    properties_found: int | None  # số chỗ ở còn phòng kênh báo cho đêm đó (con số tin cậy)
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


class CityHotelsOut(BaseModel):
    stay_date: date
    area_id: int
    total: int
    items: list[CityHotelOut]
