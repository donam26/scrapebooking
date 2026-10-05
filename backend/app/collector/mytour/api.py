"""API khách sạn của Mytour (apis.tripi.vn, nền tảng Tripi): header ký appHash và body request.
Thuần, không I/O."""

import base64
import hashlib
from datetime import date, timedelta
from typing import Any

API_BASE = "https://apis.tripi.vn/hotels"
AVAILABILITY_PATH = "/v3/rooms/availability"
DETAIL_PATH = "/v3/hotels/detail"
SUGGEST_PATH = "/v3/suggestions/auto-complete"
HOME_URL = "https://mytour.vn/"

CODE_OK = 200
CODE_HOTEL_NOT_FOUND = 4103  # "Khách sạn không tồn tại."
# 3004 "Hash không tồn tại": appHash sai → khoá web đã đổi, cập nhật _WEB_SECRET.

# Khoá tĩnh trong JS web của Mytour (_app-*.js, hàm sinh header appHash, nhánh "website").
# Mytour deploy bản mới có thể đổi khoá: tìm lại bằng grep "appHash" trong _app-*.js.
_WEB_SECRET = "@Zz8qt5CzUlyg#$RK4YJmW5!I@yYSaVf"


def app_hash(now_s: float) -> str:
    """base64(sha256("<unix giây làm tròn xuống 5 phút>:<khoá web>")), như trình duyệt tính."""
    t = int(now_s)
    t -= t % 300
    return base64.b64encode(hashlib.sha256(f"{t}:{_WEB_SECRET}".encode()).digest()).decode()


def api_headers(device_id: str, currency: str, now_s: float) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi",
        "appId": "mytour-web",
        "appHash": app_hash(now_s),
        "caid": "17",
        "countryCode": "VN",
        "currency": currency,
        "deviceId": device_id,
        "deviceInfo": "PC-Web",
        "lang": "vi",
        "platform": "website",
        "version": "1.0",
        "Origin": "https://mytour.vn",
        "Referer": HOME_URL,
    }


def availability_body(hotel_id: int, checkin: date, nights: int, adults: int) -> dict[str, Any]:
    """Body POST rooms/availability y như trang chi tiết gửi (1 phòng, 0 trẻ em)."""
    checkout = checkin + timedelta(days=nights)
    return {
        "checkIn": checkin.strftime("%d-%m-%Y"),
        "checkOut": checkout.strftime("%d-%m-%Y"),
        "adults": adults,
        "children": 0,
        "rooms": 1,
        "hotelId": hotel_id,
        "isSeo": False,
        "useBasePrice": False,
        "includeD2cRoom": True,
        "allowAffiliate": True,
    }
