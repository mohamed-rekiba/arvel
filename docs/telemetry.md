# Telemetry

arvel ships first-class **OpenTelemetry** for all three signals — **traces, metrics, and logs**. You
point it at any **OTLP** backend — Grafana (Tempo for traces · Mimir/Prometheus for metrics · Loki for
logs), the OpenTelemetry Collector, Jaeger, Honeycomb — and arvel exports there. There's no vendor
lock-in and no proprietary agent: it's the open OTLP wire format, so you choose (and change) the
backend in config. Each signal can be toggled independently.

Telemetry is **off by default** and costs nothing until you turn it on — `opentelemetry` is only
imported when enabled, so a default app stays light.

## Enable it

Install the extra and switch it on in `config/telemetry.py`:

```bash
uv add 'arvel[telemetry]'
```

```python
# config/telemetry.py
from arvel import env

config = {
    "enabled": env("OTEL_ENABLED", True),
    "service_name": env("OTEL_SERVICE_NAME", env("APP_NAME", "arvel")),
    "exporter": env("OTEL_TRACES_EXPORTER", "otlp"),       # otlp | console | memory
    "endpoint": env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"),
    "sentry_dsn": env("SENTRY_DSN", ""),                   # optional: errors → Sentry
}
```

The `TelemetryServiceProvider` (auto-registered) reads this at boot and sets up the global tracer
provider with a `service.name` resource and a batched span exporter. Nothing else to wire.

## Exporters

| `exporter` | Use it for | Notes |
|------------|-----------|-------|
| `otlp` | **Production.** Ships spans over OTLP/HTTP to `endpoint`. | Default. Works with Grafana Alloy, the OTel Collector, Jaeger, Honeycomb, … |
| `console` | Local dev. | Prints spans to stdout. |
| `memory` | Tests. | Buffers spans in process for assertions. |

## Automatic request tracing

When telemetry is on, every HTTP request is automatically wrapped in a **SERVER span** — no setup. The
span carries `http.request.method`, `url.path`, and `http.response.status_code`; a 5xx (or a raised
handler) marks it as an error. Incoming **W3C `traceparent`** headers are honored, so a request shows up
as one distributed trace across services, and any spans you create inside a handler nest under it.

This is wired by a framework middleware that runs outermost; it's a zero-cost passthrough while
telemetry is off.

## Creating spans

For finer detail inside a request (or in jobs, commands, etc.), use the `tracer()` helper — it returns a
standard OpenTelemetry tracer and its spans nest under the request span automatically:

```python
from arvel.telemetry import tracer

with tracer().start_as_current_span("checkout") as span:
    span.set_attribute("order.id", order.id)
    await process(order)
```

Spans are exported through whichever exporter you configured — the same code runs in dev (console)
and production (OTLP → Grafana).

## Metrics

Use the `meter()` helper to record metrics — counters, histograms, gauges:

```python
from arvel.telemetry import meter

orders = meter().create_counter("orders.placed")
orders.add(1, {"plan": "pro"})
```

Metrics are exported on an interval to your OTLP backend (Grafana Mimir/Prometheus, …) via the same
`endpoint` — the `/v1/metrics` path is derived automatically.

## Logs

When telemetry is on, arvel's own `Log` is exported over OTLP (to Grafana Loki, …) **with trace context
attached** — so a log line is linked to the trace (and span) it happened in; you can jump from a span in
Tempo straight to its logs. Bound fields ride along as log attributes. Just log as usual:

```python
from arvel import Log

Log.info("checkout complete", order_id=order.id)   # exported + correlated to the active trace
```

This works by bridging arvel's structlog pipeline into OpenTelemetry; standard-library `logging` is
exported too. Your normal console/JSON log output on stdout is unaffected — the OTLP export is
additional.

## Choosing signals

All three signals are on by default when telemetry is enabled. Turn any off in config:

```python
config = {"enabled": True, "endpoint": "...", "metrics": False, "logs": False}  # traces only
```

## Sending to Grafana

Run a collector that accepts OTLP and forwards to Grafana's stores, then set `endpoint` to it:

```
                              ┌─▶ Tempo  (traces)  ┐
your app ─OTLP/HTTP─▶ Alloy / ─┼─▶ Mimir  (metrics) ┼─▶ Grafana
            Collector         └─▶ Loki   (logs)    ┘
```

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318/v1/traces
```

You set the **traces** endpoint; arvel derives the sibling `/v1/metrics` and `/v1/logs` paths from it.
Any OTLP-compatible pipeline works the same way — swap the endpoint to change backends.

## Errors → Sentry

Set `sentry_dsn` (needs `sentry-sdk`, included in the `[telemetry]` extra) and arvel initializes
Sentry at boot for error reporting, alongside OTLP tracing.

## Common mistakes & gotchas

- **Forgetting the extra.** Tracing needs `arvel[telemetry]`; without it, enabling telemetry raises an
  import error for `opentelemetry`.
- **Wrong OTLP path.** The HTTP exporter wants the full traces path, e.g.
  `http://host:4318/v1/traces` — not just `http://host:4318`.
- **Expecting spans while disabled.** `tracer()` always returns a tracer, but with telemetry off it's a
  no-op (spans go nowhere). Turn on `enabled` to export.
- **Auto-instrumentation scope.** HTTP requests are auto-traced; database queries and other internals
  are not (yet). Wrap those with `tracer()` where you want the detail.
