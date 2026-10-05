from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Khoá tĩnh nằm trong JS web của các kênh (không phải bí mật tài khoản). Kênh deploy bản mới có thể
# đổi: đặt qua env (AGODA_INITIATOR_API_KEY, MYTOUR_WEB_SECRET…) để không phải build lại.
AGODA_INITIATOR_API_KEY = "b3949fd5-9553-4b4e-b221-48be2a1b84a8"  # header ag-initiator-api-key
AGODA_INITIATOR_VERSION = "6_0"  # header ag-initiator-version
# Khoá sinh header appHash (hàm trong _app-*.js, nhánh "website"); đổi → API trả mã 3004.
MYTOUR_WEB_SECRET = "@Zz8qt5CzUlyg#$RK4YJmW5!I@yYSaVf"


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

    # Đa kênh (D2, D9, D12)
    scan_currency: str = "VND"  # toàn hệ thống: listing dùng chung giữa tenant, không quy đổi
    worker_channel: str = "booking"  # kênh của tiến trình worker này (một hàng đợi mỗi kênh)
    # Ngân sách request/phút toàn hệ thống theo kênh, VD "booking=40,agoda=30"; thiếu = default.
    channel_budgets: str = ""
    channel_budget_default_per_minute: int = 40
    # Tự ngắt kênh: tỉ lệ chặn trong 15 phút vượt ngưỡng (đủ mẫu) thì dừng kênh `pause` phút.
    channel_block_rate_threshold: float = 0.2
    channel_block_min_probes: int = 20
    channel_pause_minutes: int = 30
    # Listing chỉ thành `broken` sau N lần kênh báo "không tồn tại" liên tiếp (404 thật / mã rõ
    # ràng); một trang challenge trả 200 không giết listing. Probe có dữ liệu đặt lại đếm.
    listing_not_found_threshold: int = 3
    # Khoá web của kênh (xem hằng số đầu file).
    agoda_initiator_api_key: str = AGODA_INITIATOR_API_KEY
    agoda_initiator_version: str = AGODA_INITIATOR_VERSION
    mytour_web_secret: str = MYTOUR_WEB_SECRET
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

    # Gợi ý giá (app/market/price_suggest.py `SuggestionThresholds`): ngưỡng luật, đổi không cần
    # sửa code. Chỉ số giá = giá bạn / trung vị đối thủ × 100; tỉ lệ là 0..1; mức đổi là %.
    suggest_index_raise_below: float = 97.0
    suggest_index_hold_above: float = 110.0
    suggest_index_lower_above: float = 120.0
    suggest_sold_share_tight: float = 0.5
    suggest_sold_share_hold: float = 0.3
    suggest_comp_occ_tight: float = 0.85
    suggest_comp_occ_hold: float = 0.75
    suggest_pace_fast: float = 0.15
    suggest_pace_hold: float = 0.1
    suggest_own_occ_plenty: float = 0.6
    suggest_change_min_pct: int = 5
    suggest_change_max_raise_pct: int = 15
    suggest_change_max_lower_pct: int = 10

    # API (giai đoạn 2)
    jwt_secret: str = "change-me"
    jwt_ttl_hours: int = 12
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"
    api_port: int = 8000
    # Bảo mật (phase 2). `app_env=prod`: API từ chối khởi động với jwt_secret mặc định/ngắn,
    # cookie không secure hay CORS `*`; /docs tắt; /metrics cần METRICS_TOKEN.
    app_env: str = "dev"  # dev | staging | prod
    metrics_token: str = ""
    # Chống dò mật khẩu: số lần thử đăng nhập mỗi phút theo IP và theo email, cộng trần theo giờ.
    login_per_minute_per_ip: int = 10
    login_per_minute_per_email: int = 5
    login_per_hour_per_email: int = 20
    password_reset_ttl_minutes: int = 30
    # Nhập PMS: trần kích thước tệp và số dòng (chống OOM bằng XLSX bomb), số lỗi lưu lại.
    pms_max_upload_bytes: int = 5 * 1024 * 1024
    pms_max_rows: int = 5000
    pms_max_errors_stored: int = 200
    # Hạn mức mặc định mỗi tenant (ghi đè bằng tenants.limits): số khách sạn theo dõi, số lần
    # "Quét ngay" và số bản tin theo yêu cầu mỗi ngày (giờ tenant).
    quota_max_hotels: int = 25
    quota_manual_scans_per_day: int = 6
    quota_insights_per_day: int = 5

    # AI insight (giai đoạn 3) — OpenRouter (Chat Completions, OpenAI-compatible)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-6-luna"
    openrouter_reasoning_effort: str = "medium"
    openrouter_app_name: str = "scrapebooking-insight"  # header X-Title (tùy chọn)
    openrouter_site_url: str = ""  # header HTTP-Referer (tùy chọn)
    # Giới hạn một lần gọi: trần token đầu ra, timeout HTTP (SDK thử lại 1 lần), số khách sạn
    # đưa vào đầu vào (self trước, rồi đối thủ theo thứ tự watchlist).
    openrouter_max_output_tokens: int = 4096
    openrouter_timeout_seconds: float = 120.0
    insight_max_hotels: int = 25

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
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
