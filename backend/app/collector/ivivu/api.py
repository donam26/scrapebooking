"""Endpoint và payload API JSON của ivivu (thuần)."""

from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

API_BASE = "https://apiportal.ivivu.com"
PRICE_URL = f"{API_BASE}/web_prot/pay/api/contracting/HotelSearchReqContractAppV2"
SEARCH_URL = f"{API_BASE}/web_prot/gate/search/searchhotel"
TOP_SALE_URL = f"{API_BASE}/web_prot/gate/mobile/OliviaApis/TopSale24hByHotel"
ORIGIN = "https://www.ivivu.com"
NATIONALITY_VN = 82  # nationalityID trang web gửi cho khách Việt Nam


def price_request(hotel_id: int, checkin: date, nights: int, adults: int) -> dict[str, Any]:
    """Payload y như trang web gửi (1 phòng, 0 trẻ em, khách VN, không combo); chỉ đổi khách sạn,
    ngày và số người lớn. Các cờ get*/is* bật mọi nguồn bán (Agoda, Hotelbeds, Vinpearl HMS…)."""
    return {
        "hotelID": hotel_id,
        "roomNumber": 1,
        "isLeadingPrice": 1,
        "supplier": "IVIVU",
        "checkInDate": checkin.isoformat(),
        "checkOutDate": (checkin + timedelta(days=nights)).isoformat(),
        "nationalityID": NATIONALITY_VN,
        "isPackageRate": False,
        "isPackageRateInternal": False,
        "isFenced": False,
        "getVinHms": 1,
        "getRateMGB": 1,
        "getSMD": 1,
        "isB2B": True,
        "isSeri": True,
        "isAgoda": True,
        "isOccWithBed": True,
        "getRateHLS": 1,
        "roomsRequest": [
            {
                "roomIndex": 1,
                "adults": {"label": 1, "value": adults},
                "child": {"label": 0, "value": 0},
                "ageChilds": [],
            }
        ],
        "isFlashsale": False,
        "onlyAl": 0,
        "ggLink": False,
        "getRateHBED": 1,
        "getRateExtranet": 1,
        "TagId": "",
    }


def price_headers(token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN",
        "Origin": ORIGIN,
        "Referer": ORIGIN + "/",
        "X-Client-Source": "IVIVU_WEB",
    }
    if token:  # rỗng: ivivu đang tắt kiểm tra bot (FlagSetting flagOn=0)
        headers["X-ivv-key"] = token
    return headers


def search_url(keyword: str) -> str:
    return f"{SEARCH_URL}?{urlencode({'keyword': keyword})}"


def top_sale_url(hotel_id: int) -> str:
    return f"{TOP_SALE_URL}?{urlencode({'hotelId': hotel_id})}"
