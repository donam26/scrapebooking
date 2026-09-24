from prometheus_client import Counter, Gauge, Histogram, start_http_server

PROBES_TOTAL = Counter("sb_probes_total", "Probes by status and method", ["status", "method"])
PROBE_DURATION = Histogram(
    "sb_probe_duration_seconds", "Probe duration", buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60)
)
SESSIONS_CREATED = Counter("sb_sessions_created_total", "Sessions bootstrapped", ["country"])
SESSIONS_RETIRED = Counter("sb_sessions_retired_total", "Sessions retired", ["reason"])
JOBS_TOTAL = Counter("sb_jobs_total", "Hotel jobs by final status", ["status"])
RUNS_CREATED = Counter("sb_runs_created_total", "Scan runs created")
QUEUE_DEPTH = Gauge("sb_scheduler_last_run_jobs", "Jobs enqueued by the last created run")
ANALYTICS_RUNS = Counter("sb_analytics_runs_total", "Analytics runs by status", ["status"])
EVENTS_TOTAL = Counter("sb_events_total", "Availability events generated", ["event_type"])
INSIGHTS_TOTAL = Counter("sb_insights_total", "Insight generations by status", ["status"])


def start_metrics_server(port: int) -> None:
    start_http_server(port)
