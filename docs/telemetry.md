# Telemetry

arvel ships first-class **OpenTelemetry** tracing. You point it at any **OTLP** backend — Grafana
(Tempo/Alloy), the OpenTelemetry Collector, Jaeger, Honeycomb — and arvel exports spans there. There's
no vendor lock-in and no proprietary agent: it's the open OTLP wire format, so you choose (and change)
the backend in config.

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

## Creating spans

Use the `tracer()` helper anywhere — it returns a standard OpenTelemetry tracer:

```python
from arvel.telemetry import tracer

with tracer().start_as_current_span("checkout") as span:
    span.set_attribute("order.id", order.id)
    await process(order)
```

Spans are exported through whichever exporter you configured — the same code runs in dev (console)
and production (OTLP → Grafana).

## Sending to Grafana

Run a collector that accepts OTLP and forwards to Grafana's stores, then set `endpoint` to it:

```
your app ──OTLP/HTTP──▶ Grafana Alloy / OTel Collector ──▶ Tempo (traces) ──▶ Grafana
```

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318/v1/traces
```

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
- **Auto-instrumentation.** arvel sets up the exporter and gives you manual spans; it does not yet
  auto-instrument every request/query. Wrap the spans you care about with `tracer()`.
