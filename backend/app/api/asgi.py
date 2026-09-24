"""Entrypoint cho uvicorn: `uvicorn app.api.asgi:app`."""

from app.api.main import create_app

app = create_app()
