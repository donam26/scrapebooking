from app.collector.booking.selectors import extract_csrf_token


def test_extract_csrf_single_quotes() -> None:
    html = "<script>var x = {b_csrf_token: 'abc.def-123'};</script>"
    assert extract_csrf_token(html) == "abc.def-123"


def test_extract_csrf_double_quotes_json_style() -> None:
    html = '<script>{"b_csrf_token": "tok_9"}</script>'
    assert extract_csrf_token(html) == "tok_9"


def test_extract_csrf_missing() -> None:
    assert extract_csrf_token("<html></html>") is None
