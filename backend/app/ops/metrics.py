from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Tên metric đang dùng trong Grafana (infra/grafana/provisioning/dashboards/json): giữ nguyên.
PROBES_TOTAL = Counter("sb_probes_total", "Probes by status and method", ["status", "method"])
PROBE_DURATION = Histogram(
    "sb_probe_duration_seconds", "Probe duration", buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60)
)
SESSIONS_CREATED = Counter("sb_sessions_created_total", "Sessions bootstrapped", ["country"])
SESSIONS_RETIRED = Counter("sb_sessions_retired_total", "Sessions retired", ["reason"])
JOBS_TOTAL = Counter("sb_jobs_total", "Hotel jobs by final status", ["status"])
RUNS_CREATED = Counter("sb_runs_created_total", "Scan runs created")
ANALYTICS_RUNS = Counter("sb_analytics_runs_total", "Analytics runs by status", ["status"])
EVENTS_TOTAL = Counter("sb_events_total", "Availability events generated", ["event_type"])
INSIGHTS_TOTAL = Counter("sb_insights_total", "Insight generations by status", ["status"])
OCCUPANCY_FAILURES = Counter("sb_occupancy_estimate_failures_total", "Occupancy estimate failures")

# Scheduler (một giá trị mỗi tick; quy tắc cảnh báo ở infra/prometheus/rules/ops.yml).
# Hằng này trước tên QUEUE_DEPTH dù đo số job của run vừa tạo; độ sâu hàng đợi thật là
# ARQ_QUEUE_DEPTH bên dưới.
LAST_RUN_JOBS = Gauge("sb_scheduler_last_run_jobs", "Jobs enqueued by the last created run")
SCHEDULER_TICKS = Counter(
    "sb_scheduler_ticks_total", "Scheduler ticks by outcome (ok, error, standby)", ["outcome"]
)
SCHEDULER_TICK_SECONDS = Histogram(
    "sb_scheduler_tick_seconds",
    "Scheduler tick duration (DB work + alerts + proxy check)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
ARQ_QUEUE_DEPTH = Gauge(
    "sb_arq_queue_depth", "Jobs waiting in an arq queue (ZCARD, measured each tick)", ["queue"]
)
RUNS_EXPIRED = Counter("sb_runs_expired_total", "Scan runs closed by the scheduler past deadline")
ANALYTICS_LAG = Gauge(
    "sb_analytics_lag_seconds",
    "Age of the oldest finished scan run (last 7 days) still waiting for analytics; 0 when none",
)
BACKUPS_TOTAL = Counter("sb_backups_total", "Postgres backups by status (ok, error)", ["status"])


def start_metrics_server(port: int) -> None:
    start_http_server(port)
