"""Chấm điểm ứng viên listing chéo kênh (D8): giống tên + gần toạ độ. Thuần, dùng chung mọi kênh."""

import math
import re
import unicodedata
from difflib import SequenceMatcher

# Từ chung chung không giúp phân biệt khách sạn.
_STOPWORDS = {
    "hotel", "hotels", "khach", "san", "resort", "khu", "nghi", "duong", "the", "and", "spa",
    "by", "va", "saigon", "sai", "gon", "hcm", "city",
}  # fmt: skip


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.lower().replace("đ", "d"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    words = re.findall(r"[a-z0-9]+", text)
    return " ".join(w for w in words if w not in _STOPWORDS)


# Tiền tố loại hình làm API gợi ý không tìm ra ("Khu nghỉ dưỡng Melia…" → rỗng trên Booking).
_GENERIC_PREFIX = re.compile(
    r"^\s*(khu\s+nghỉ\s+dưỡng|khu\s+nghi\s+duong|khách\s+sạn|khach\s+san|resort|hotel|"
    r"nhà\s+nghỉ|căn\s+hộ|biệt\s+thự)\s+",
    re.IGNORECASE,
)


def search_names(name: str) -> list[str]:
    """Các biến thể tên để gọi API gợi ý của kênh, thử lần lượt: nguyên tên, bỏ tiền tố loại hình,
    và bản không dấu."""
    out: list[str] = []
    stripped = _GENERIC_PREFIX.sub("", name).strip()
    plain = unicodedata.normalize("NFKD", stripped.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    for v in (name.strip(), stripped, plain):
        if v and v not in out:
            out.append(v)
    return out


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    return max(seq, jaccard)


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def match_score(
    query_name: str,
    candidate_name: str,
    query_latlng: tuple[float, float] | None = None,
    candidate_latlng: tuple[float, float] | None = None,
) -> float:
    """0..1. Có toạ độ cả hai: 60% tên + 40% khoảng cách (≤150 m = 1, ≥2 km = 0)."""
    name = name_similarity(query_name, candidate_name)
    if query_latlng is None or candidate_latlng is None:
        return round(name, 3)
    d = distance_m(*query_latlng, *candidate_latlng)
    geo = 1.0 if d <= 150 else max(0.0, 1 - (d - 150) / 1850)
    return round(0.6 * name + 0.4 * geo, 3)
