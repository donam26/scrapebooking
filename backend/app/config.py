from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str
    test_database_url: str = "postgresql+asyncpg://app:app@localhost:5432/scrapebooking_test"
    redis_url: str

    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "raw-html"

    proxy_url_template: str
    session_max_age_minutes: int = 20
    session_max_requests: int = 400
    request_min_interval_seconds: float = 2.0
    request_jitter_seconds: float = 1.0
    page_dropdown_cap: int = 10
    run_deadline_minutes: int = 90
    default_adults: int = 2

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    metrics_port: int = 9100
    log_level: str = "INFO"
    playwright_headless: bool = True

    # Analytics (giai đoạn 2)
    low_stock_threshold: int = 3
    price_change_threshold_pct: float = 3.0

    # API (giai đoạn 2)
    jwt_secret: str = "change-me"
    jwt_ttl_hours: int = 12
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"
    api_port: int = 8000

    # AI insight (giai đoạn 3)
    openai_api_key: str = ""
    openai_model: str = "gpt-6-luna"
    openai_reasoning_effort: str = "medium"
    insight_use_batch: bool = True

    # Backup (giai đoạn 5)
    backup_bucket: str = "pg-backups"
    backup_keep: int = 14

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
