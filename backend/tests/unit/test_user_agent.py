from app.collector.booking.playwright_bootstrap import normalize_user_agent

HEADLESS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) HeadlessChrome/153.0.8010.12 Safari/537.36"
)


def test_headless_marker_removed() -> None:
    # Booking nhận ra "HeadlessChrome" và 301 về trang không có ngày (bỏ checkin/checkout).
    ua = normalize_user_agent(HEADLESS)
    assert "Headless" not in ua
    assert "Chrome/153.0.8010.12" in ua


def test_normal_user_agent_unchanged() -> None:
    ua = HEADLESS.replace("HeadlessChrome", "Chrome")
    assert normalize_user_agent(ua) == ua
