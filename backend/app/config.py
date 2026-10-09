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

    # Một hoặc nhiều proxy, cách nhau dấu phẩy; mỗi session mới lấy proxy kế tiếp (xoay vòng).
    proxy_url_template: str
    session_max_age_minutes: int = 20
    session_max_requests: int = 400
    request_min_interval_seconds: float = 2.0
    request_jitter_seconds: float = 1.0
    page_dropdown_cap: int = 10
    run_deadline_minutes: int = 90
    default_adults: int = 2

    # Booking.com (kênh duy nhất)
    scan_currency: str = "VND"  # toàn hệ thống: listing dùng chung giữa tenant, không quy đổi
    worker_channel: str = "booking"  # hàng đợi của worker (chỉ còn "booking")
    # Ngân sách request/phút toàn hệ thống, VD "booking=40"; thiếu = default.
    channel_budgets: str = ""
    channel_budget_default_per_minute: int = 40
    # Tự ngắt kênh: tỉ lệ chặn trong 15 phút vượt ngưỡng (đủ mẫu) thì dừng kênh `pause` phút.
    channel_block_rate_threshold: float = 0.2
    channel_block_min_probes: int = 20
    channel_pause_minutes: int = 30
    # Quét theo tầng: đêm trong `tier_near_days` ngày quét mọi lượt; tới `tier_mid_days` chỉ quét
    # khi lần dùng được gần nhất cũ hơn `tier_mid_max_age_hours`; xa hơn: `tier_far_max_age_hours`.
    tier_near_days: int = 14
    tier_mid_days: int = 60
    tier_mid_max_age_hours: int = 20
    tier_far_max_age_hours: int = 66
    # Thị trường toàn thành phố (app/marketscan): giờ địa phương của tenant quét danh sách và tạo
    # run quét chi tiết; số job chi tiết chờ sẵn trong hàng đợi kênh (để run thường xen vào);
    # hạn chót riêng của run thị trường (vài trăm khách sạn, dài hơn run thường).
    market_list_time: str = "03:00"
    market_detail_time: str = "05:00"
    market_detail_inflight: int = 4
    # Đêm khám phá (số ngày kể từ đêm đầu của vòng quét danh sách): thêm các lát bộ lọc × thứ tự
    # để mở rộng danh sách khách sạn của khu vực, tối đa `market_areas.max_pages` request.
    market_discovery_night: int = 7
    # Trần tải phía server (áp khi tạo/sửa khu vực và khi chạy): số KS quét chi tiết, số request
    # của đêm khám phá, số khu vực mỗi tenant (operator không bị giới hạn số khu vực).
    market_max_hotels: int = 500
    market_max_pages: int = 100
    market_max_areas_per_tenant: int = 3
    market_list_retention_days: int = 120  # xoá lượt quét danh sách + giá cũ hơn
    market_search_per_minute: int = 10  # tìm địa điểm (gọi Booking thật) mỗi tenant mỗi phút
    market_run_deadline_hours: int = 20

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

    # AI insight (giai đoạn 3) — OpenRouter (Chat Completions, OpenAI-compatible)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-6-luna"
    openrouter_reasoning_effort: str = "medium"
    openrouter_app_name: str = "scrapebooking-insight"  # header X-Title (tùy chọn)
    openrouter_site_url: str = ""  # header HTTP-Referer (tùy chọn)
    insight_use_batch: bool = True

    # Thẻ thời tiết Terminal+ (OpenWeather, gói miễn phí). Để trống thì thẻ báo cần cấu hình.
    openweather_api_key: str = ""

    # Thông báo email. Không đặt SMTP_HOST thì không gửi (nhật ký ghi "skipped").
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none
    smtp_timeout_seconds: float = 20.0
    # Gốc dashboard cho liên kết trong email (không có dấu / cuối).
    app_base_url: str = "http://localhost:3000"
    # Email nhận cảnh báo vận hành (proxy hỏng, kênh bị chặn, lỡ lịch quét), cách nhau dấu phẩy.
    ops_alert_emails: str = ""
    # Webhook chat của đội vận hành (Slack/Discord/Google Chat…), cách nhau dấu phẩy.
    ops_alert_webhook_urls: str = ""

    # Zalo ZNS (roadmap 3.3): OA doanh nghiệp xác thực + Zalo Cloud nạp trước + template đã duyệt.
    # Token sống ~25h: đặt app id/secret/refresh token để tự làm mới, hoặc chỉ access token.
    zalo_zns_access_token: str = ""
    zalo_app_id: str = ""
    zalo_app_secret: str = ""
    zalo_refresh_token: str = ""
    # Mã template theo loại tin, VD "alerts=123,daily_insight=456,data_stale=789,test=123".
    zalo_zns_templates: str = ""
    zalo_zns_cost_vnd: int = 300  # đơn giá ước tính mỗi tin gửi thành công (ghi vào nhật ký)

    # Backup (giai đoạn 5)
    backup_bucket: str = "pg-backups"
    backup_keep: int = 14

    @property
    def proxy_templates(self) -> list[str]:
        return [p.strip() for p in self.proxy_url_template.split(",") if p.strip()]

    def channel_budget(self, channel: str) -> int:
        for pair in self.channel_budgets.split(","):
            code, _, value = pair.partition("=")
            if code.strip() == channel and value.strip().isdigit():
                return int(value)
        return self.channel_budget_default_per_minute

    @property
    def ops_alert_email_list(self) -> list[str]:
        return [e.strip() for e in self.ops_alert_emails.split(",") if e.strip()]

    @property
    def zalo_zns_configured(self) -> bool:
        has_token = bool(self.zalo_zns_access_token) or bool(
            self.zalo_app_id and self.zalo_app_secret and self.zalo_refresh_token
        )
        return has_token and bool(self.zalo_zns_templates.strip())

    @property
    def ops_alert_webhook_url_list(self) -> list[str]:
        return [u.strip() for u in self.ops_alert_webhook_urls.split(",") if u.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
