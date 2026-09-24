"""Xuất OpenAPI của API ra docs/api/openapi.json (dashboard sinh type TypeScript từ file này).

Dùng: cd backend && uv run python scripts/export_openapi.py
"""

import json
from pathlib import Path

from app.api.main import create_app
from app.config import Settings

OUT = Path(__file__).parent.parent.parent / "docs" / "api" / "openapi.json"


def build_spec() -> dict:  # type: ignore[type-arg]
    app = create_app(
        settings=Settings(_env_file=None, database_url="x", redis_url="x", proxy_url_template="x")
    )
    return app.openapi()


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build_spec(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
