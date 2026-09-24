from app.config import Settings


def test_settings_read_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/1")
    monkeypatch.setenv("PROXY_URL_TEMPLATE", "http://a-{country}-{session}:b@p:1")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/db"
    assert s.redis_url == "redis://h:6379/1"
    assert s.session_max_requests == 400
    assert s.page_dropdown_cap == 10
    assert s.request_min_interval_seconds == 2.0


def test_settings_defaults(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/1")
    monkeypatch.setenv("PROXY_URL_TEMPLATE", "http://a-{country}-{session}:b@p:1")
    s = Settings(_env_file=None)
    assert s.default_adults == 2
    assert s.run_deadline_minutes == 90
    assert s.minio_bucket == "raw-html"
    assert s.low_stock_threshold == 3
    assert s.price_change_threshold_pct == 3.0
    assert s.cors_origin_list == ["http://localhost:3000"]
