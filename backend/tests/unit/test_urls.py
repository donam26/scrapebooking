from datetime import date

from app.collector.booking.urls import build_hotel_url, canonical_url, pagename
from tests.fakes import booking_listing

HOTEL = booking_listing(slug="vn/the-reverie-saigon")


def test_build_hotel_url() -> None:
    url = build_hotel_url(HOTEL, checkin=date(2026, 10, 5), nights=2, adults=2, currency="VND")
    assert url == (
        "https://www.booking.com/hotel/vn/the-reverie-saigon.en-gb.html"
        "?checkin=2026-10-05&checkout=2026-10-07&group_adults=2&no_rooms=1"
        "&group_children=0&selected_currency=VND&lang=en-gb"
    )


def test_pagename_and_canonical_url() -> None:
    assert pagename(HOTEL) == "the-reverie-saigon"
    assert canonical_url("vn/the-reverie-saigon") == (
        "https://www.booking.com/hotel/vn/the-reverie-saigon.html"
    )
