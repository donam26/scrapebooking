"""docs/api/openapi.json phải khớp với app: dashboard sinh type từ file đó."""

import json
from pathlib import Path

from app.api.main import create_app
from app.config import Settings

SNAPSHOT = Path(__file__).parent.parent.parent.parent / "docs" / "api" / "openapi.json"


def test_openapi_snapshot_is_current() -> None:
    app = create_app(
        settings=Settings(_env_file=None, database_url="x", redis_url="x", proxy_url_template="x")
    )
    current = app.openapi()
    stored = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert current["paths"].keys() == stored["paths"].keys(), (
        "chạy: cd backend && uv run python scripts/export_openapi.py"
    )
    assert current["components"]["schemas"] == stored["components"]["schemas"], (
        "schema đổi: chạy scripts/export_openapi.py rồi npm run gen:api trong dashboard"
    )
