"""Telemetry config — OpenTelemetry trace export (disabled by default).

Set `enabled` true and point `endpoint` at any OTLP/HTTP collector — Grafana Alloy, the OpenTelemetry
Collector, Jaeger, Honeycomb, … — to export traces; arvel is not tied to one vendor. `exporter` is
`otlp` (production), `console` (dev), or `memory` (tests). Needs the `[telemetry]` extra. A Sentry DSN
(optional) also routes errors to Sentry.
"""

from arvel import env

config = {
    "enabled": env("OTEL_ENABLED", False),
    "service_name": env("OTEL_SERVICE_NAME", env("APP_NAME", "arvel")),
    "exporter": env("OTEL_TRACES_EXPORTER", "otlp"),
    "endpoint": env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"),
    # Metrics delivery: push (OTLP, default) or pull — set true to expose a Prometheus `/metrics`
    # scrape endpoint instead (needs the `[telemetry]` extra's prometheus packages).
    "prometheus": env("OTEL_PROMETHEUS", False),
    "sentry_dsn": env("SENTRY_DSN", ""),
}
