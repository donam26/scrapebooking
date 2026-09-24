import pytest

from app.collector.fetch import FetchOutcome, classify_response


@pytest.mark.parametrize(
    "status,text,expected",
    [
        (200, "<html><table id='hprt-table'></table></html>", FetchOutcome.OK),
        (403, "", FetchOutcome.BLOCKED),
        (429, "", FetchOutcome.BLOCKED),
        (503, "", FetchOutcome.BLOCKED),
        (202, "<html>challenge</html>", FetchOutcome.BLOCKED),
        (200, "<script src='https://x.awswaf.com/challenge.js'></script>", FetchOutcome.BLOCKED),
        (200, "<title>Pardon Our Interruption</title>", FetchOutcome.BLOCKED),
        (404, "", FetchOutcome.NOT_FOUND),
        (500, "", FetchOutcome.ERROR),
    ],
)
def test_classify(status: int, text: str, expected: FetchOutcome) -> None:
    assert classify_response(status, text) == expected
