"""Trang kết quả tìm kiếm Booking (thị trường toàn thành phố) trên trang thật đã rút gọn.

Fixture: searchresults.en-gb.html cho Ho Chi Minh City (dest_id -3730078, city), đêm 2026-10-09,
2 người lớn, VND, trang đầu; bắt 2026-10-02 qua proxy dân dụng VN đúng đường đi của worker. Số kỳ
vọng đọc tay từ thẻ HTML (khối giá, "Scored …", "N reviews").
"""

import gzip
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.marketscan.destinations import parse_destinations
from app.marketscan.parser import district_of, parse_search_page
from app.marketscan.urls import build_search_url


@pytest.fixture(scope="module")
def html() -> str:
    path = (
        Path(__file__).parent.parent / "fixtures" / "html" / "searchresults_hcmc_2026-10-09.html.gz"
    )
    return gzip.decompress(path.read_bytes()).decode("utf-8")


def test_search_url_has_one_night_two_adults_vnd_filters_order_and_offset_zero() -> None:
    url = build_search_url(
        "-3730078", "city", date(2026, 10, 9), order="price", nflt="class=3;ht_id=204"
    )
    parsed = urlparse(url)
    assert parsed.netloc == "www.booking.com" and parsed.path == "/searchresults.en-gb.html"
    assert "nflt=class%3D3%3Bht_id%3D204" in parsed.query
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert q == {
        "dest_id": "-3730078",
        "dest_type": "city",
        "checkin": "2026-10-09",
        "checkout": "2026-10-10",
        "group_adults": "2",
        "no_rooms": "1",
        "group_children": "0",
        "selected_currency": "VND",
        "lang": "en-gb",
        "nflt": "class=3;ht_id=204",
        "order": "price",
        "offset": "0",  # luôn có, kể cả trang đầu (tránh chế độ cuộn vô hạn)
    }
    plain = build_search_url("2088", "district", date(2026, 12, 31))
    assert "checkout=2027-01-01" in plain and plain.endswith("&offset=0")
    assert "nflt" not in plain and "order" not in plain


def test_parse_real_page_from_apollo_store(html: str) -> None:
    page = parse_search_page(html)
    assert page.source == "apollo"
    assert page.total == 3944  # "Ho Chi Minh City: 3,944 properties found"
    assert page.checkin == date(2026, 10, 9)
    assert (page.per_page, page.offset) == (25, 0)
    # Số chỗ ở theo lựa chọn bộ lọc (facet) của chính truy vấn này.
    assert {k: page.facets[k] for k in ("class=1", "class=3", "class=5")} == {
        "class=1": 105,
        "class=3": 925,
        "class=5": 100,
    }
    assert page.facets["ht_id=204"] == 1447 and page.facets["ht_id=201"] == 2016
    assert page.facets["review_score=90"] == 929 and page.facets["di=6750"] == 536
    assert len(page.cards) == 25
    assert len({c.slug for c in page.cards}) == 25

    first = page.cards[0]
    assert first.slug == "vn/ancient-luxury-amp-spa"
    assert first.url == "https://www.booking.com/hotel/vn/ancient-luxury-amp-spa.html"
    assert first.name == "Ancient Luxury Hotel & Spa"
    assert first.external_id == "17311367"
    assert (first.review_score, first.review_count) == (Decimal("8.9"), 17)
    assert first.stars == Decimal("3")
    assert first.district == "District 1"
    assert first.distance_text == "0.7 km from centre"
    assert (first.lat, first.lng) == (10.7704518, 106.6923346)
    assert first.image_url is not None
    assert first.image_url.startswith("https://cf.bstatic.com/xdata/images/hotel/")
    assert (first.price, first.currency) == (Decimal("1134000"), "VND")  # "Includes taxes"
    assert first.sold_out is False
    assert first.type_id == 204  # khách sạn

    by_slug = {c.slug: c for c in page.cards}
    # "VND 1,845,000 +VND 247,230 taxes and charges" → giá gồm thuế phí.
    assert by_slug["vn/ibis-saigon-airport"].price == Decimal("2092230")
    assert by_slug["vn/la-vela-saigon"].review_count == 9467
    assert by_slug["vn/la-vela-saigon"].stars == Decimal("5")
    # Căn hộ mới, chưa có đánh giá, không hạng sao.
    sol = by_slug["vn/de-la-sol-apartment-near-benthanh-market"]
    assert sol.review_score is None and sol.review_count is None and sol.stars is None
    assert sol.price == Decimal("1900000")  # 1900000.0001 trong kho → làm tròn đồng
    assert by_slug["vn/sai-gon-heat-2-thanh-pho-ho-chi-minh"].district is None  # chỉ có thành phố
    assert all(c.currency == "VND" and c.price for c in page.cards)


def test_html_cards_fallback_matches_apollo(html: str) -> None:
    apollo = parse_search_page(html)
    no_store = re.sub(
        r"<script[^>]*data-capla-store-data=\"apollo\".*?</script>", "", html, flags=re.S
    )
    page = parse_search_page(no_store)
    assert page.source == "html"
    assert page.total == 3944 and page.checkin is None
    assert [c.slug for c in page.cards] == [c.slug for c in apollo.cards]
    for a, b in zip(apollo.cards, page.cards, strict=True):
        assert (b.name, b.price, b.currency) == (a.name, a.price, a.currency)
        assert (b.review_score, b.review_count, b.stars) == (
            a.review_score,
            a.review_count,
            a.stars,
        )
        assert (b.district, b.distance_text) == (a.district, a.distance_text)
        assert b.external_id is None and b.lat is None and b.type_id is None  # chỉ kho Apollo có
    assert page.facets == {}


def test_empty_or_unrelated_page_has_no_cards() -> None:
    page = parse_search_page("<html><body><h1>Access denied</h1></body></html>")
    assert page.cards == [] and page.total is None


def test_district_of() -> None:
    assert district_of("District 1, Ho Chi Minh City") == "District 1"
    assert district_of("Tan Phu District, Ho Chi Minh City") == "Tan Phu District"
    assert district_of("Ho Chi Minh City") is None
    assert district_of(None) is None


def test_autocomplete_keeps_only_area_destinations() -> None:
    path = Path(__file__).parent.parent / "fixtures" / "html" / "autocomplete_ho_chi_minh_city.json"
    found = parse_destinations(json.loads(path.read_text(encoding="utf-8")))
    assert [(d.dest_id, d.dest_type) for d in found] == [
        ("-3730078", "city"),
        ("2088", "district"),
        ("6750", "district"),
    ]
    city = found[0]
    assert city.name == "Ho Chi Minh City"
    assert city.label == "Ho Chi Minh City, Ho Chi Minh Municipality, Vietnam"
    assert (city.country_code, city.nr_hotels) == ("vn", 6890)
    assert city.lat == pytest.approx(10.771475)
