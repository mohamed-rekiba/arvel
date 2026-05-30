# Debugging & Observability

Arvel ships OpenTelemetry out of the box. `ObservabilityServiceProvider` registers all three OTel
pillars — traces, metrics, and logs — during application boot. No wiring required.

## Zero-config setup

Nothing to configure for local dev. The provider boots automatically:

- Traces and metrics are wired to in-process no-op exporters when no OTLP endpoint is set.
- Logs are emitted as structured JSON to stdout at `info` level.
- SQLAlchemy and FastAPI are auto-instrumented.

## Shipping to a collector

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to forward all three signals via OTLP/gRPC:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=my-api
```

Any OTLP-compatible backend works — Jaeger, Grafana Tempo, Datadog, Honeycomb, Sentry, etc.

For authenticated endpoints, pass headers as `key=value,key2=value2`:

```env
OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=my-api-key
```

The header value is treated as a secret — it won't appear in logs or startup output.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `OTEL_SDK_DISABLED` | `false` | Set `true` to skip all OTel initialisation (useful for test environments) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(empty)_ | OTLP/gRPC collector endpoint; no-op exporter when unset |
| `OTEL_EXPORTER_OTLP_HEADERS` | _(empty)_ | `key=value,…` auth headers for the OTLP endpoint |
| `OTEL_SERVICE_NAME` | `APP_NAME` or `arvel` | `service.name` resource attribute on every signal |
| `LOG_LEVEL` | `info` | Minimum log severity: `debug`, `info`, `warning`, `error`, `critical` |
| `LOG_FORMAT` | `json` | `json` for production, `console` for local dev (colorized) |
| `LOG_UVICORN_ACCESS` | `true` | Bridge Uvicorn access logs through the OTel pipeline |
| `DB_QUERY_LOG_ENABLED` | `true` | Emit OTel spans for each SQL query |
| `DB_SLOW_QUERY_MS` | `200` | Log a `WARNING` for queries exceeding this threshold (ms) |
| `OBSERVABILITY_METRICS_ENABLED` | `false` | Expose Prometheus metrics at `/_metrics` |
| `OBSERVABILITY_METRICS_ALLOWED_CIDRS` | `127.0.0.1/32` | CIDR allowlist for `/_metrics`; returns 403 otherwise |
| `OBSERVABILITY_REQUEST_MIDDLEWARE_ENABLED` | `true` | Attach request-context middleware (adds `request_id`, span, user binding) |

## Disabling the SDK

Set `OTEL_SDK_DISABLED=true` to skip all provider initialisation. This is the recommended setting
for unit-test environments — all `Log.*` calls become no-ops with no network, no serialisation
overhead.

`boot_providers()` is idempotent: calling it multiple times in the same process (common in test
suites) always produces a consistent result. When the SDK is disabled it resets any previously
installed SDK provider, so tests that run after a SDK-enabled test still see the no-op state.

```env
# .env.test
OTEL_SDK_DISABLED=true
```

## Prometheus metrics

Enable the `/_metrics` endpoint for Prometheus scraping:

```env
OBSERVABILITY_METRICS_ENABLED=true
# Allow scraping from your Prometheus host's CIDR
OBSERVABILITY_METRICS_ALLOWED_CIDRS=10.0.0.0/8,127.0.0.1/32
```

The endpoint is protected by CIDR allowlist. Requests from outside the allowlist receive HTTP 403.

## Sensitive data

`OTEL_EXPORTER_OTLP_HEADERS` (bearer tokens, API keys) is marked `repr=False` — it won't appear
in `repr()`, logs, or the `arvel about` output.

Log lines auto-redact fields whose key matches `LOG_REDACT_FIELDS`
(`password`, `token`, `secret`, `authorization`, `api_key`, `private_key` by default).

## See also

- [Logging](logging.md) — `Log` facade, channels, and log levels.
- [Error Handling](errors.md) — how exceptions map to log entries and spans.
- [Deployment](deployment.md) — production observability setup.
