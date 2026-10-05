import pytest

from app.collector.fetch import FetchOutcome, classify_response, looks_like_html

CHALLENGE = "<html><script src='https://x.awswaf.com/challenge.js'></script></html>"


@pytest.mark.parametrize(
    "status,text,expected",
    [
        (200, "<html><table id='hprt-table'></table></html>", FetchOutcome.OK),
        (403, "", FetchOutcome.BLOCKED),
        (429, "", FetchOutcome.BLOCKED),
        (202, "<html>challenge</html>", FetchOutcome.BLOCKED),
        (200, CHALLENGE, FetchOutcome.BLOCKED),
        (200, "<title>Pardon Our Interruption</title>", FetchOutcome.BLOCKED),
        (200, "  \n<!DOCTYPE html><title>Just a moment...</title>", FetchOutcome.BLOCKED),
        (400, "<html>Access Denied</html>", FetchOutcome.BLOCKED),
        (404, "", FetchOutcome.NOT_FOUND),
        (500, "", FetchOutcome.ERROR),
        # 503 sự cố thật (không phải challenge): lỗi tạm thời, thử lại, không đốt session/proxy.
        (503, "", FetchOutcome.ERROR),
        (503, '{"error":"upstream unavailable"}', FetchOutcome.ERROR),
        # 503 mà body là trang WAF: vẫn là chặn.
        (503, CHALLENGE, FetchOutcome.BLOCKED),
        # JSON API: không quét dấu hiệu chặn trong body (mô tả khách sạn có thể chứa chữ đó).
        (200, '{"Hotels":[{"Description":"Access denied to pool after 22h"}]}', FetchOutcome.OK),
        (200, '[{"name":"verify you are a human friendly hotel"}]', FetchOutcome.OK),
        (200, "challenge.js plain text without html", FetchOutcome.OK),
    ],
)
def test_classify(status: int, text: str, expected: FetchOutcome) -> None:
    assert classify_response(status, text) == expected


def test_looks_like_html() -> None:
    assert looks_like_html("<!DOCTYPE html><html></html>")
    assert looks_like_html("\n\n  <div>x</div>")
    assert looks_like_html("garbage before <HTML lang='en'>")
    assert not looks_like_html('{"a": "<b>"}')
    assert not looks_like_html("")
