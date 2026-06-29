# Telemetry & Observability

arvel ships first-class **OpenTelemetry** for all three signals — **traces, metrics, and logs** — and
exports them over the open **OTLP** wire format to any backend: Grafana (Tempo · Mimir · Loki), the
OpenTelemetry Collector, Jaeger, Honeycomb, Datadog, … There's no proprietary agent and no vendor
lock-in; you pick (and change) the backend in config.

It is **off by default** and costs nothing until you turn it on — `opentelemetry` is imported only when
enabled, so `import arvel` and the CLI stay light. Once on, HTTP requests, database queries, and queue
jobs are traced automatically, request metrics are recorded, and your `Log` output is exported and
correlated to the trace it happened in.

## Contents

- [Quick start](#quick-start)
- [New to observability? A hands-on tour](#new-to-observability-a-hands-on-tour)
- [Configuration](#configuration)
- [Traces](#traces) — automatic + manual
- [Metrics](#metrics) — automatic + manual
- [Logs](#logs)
- [Delivery: push vs pull](#delivery-push-vs-pull)
- [Sending to Grafana](#sending-to-grafana)
- [Errors → Sentry](#errors--sentry)
- [Security](#security)
- [Common mistakes & gotchas](#common-mistakes--gotchas)

## Quick start

Install the extra and switch it on:

```bash
uv add 'arvel[telemetry]'
```

```python
# config/telemetry.py
from arvel import env

config = {
    "enabled": env("OTEL_ENABLED", True),
    "service_name": env("OTEL_SERVICE_NAME", env("APP_NAME", "blog")),
    "exporter": env("OTEL_TRACES_EXPORTER", "otlp"),                 # otlp | console | memory
    "endpoint": env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"),
}
```

That's it. The `TelemetryServiceProvider` reads this at boot and wires the tracer, meter, and logger
providers. Hit a route and you'll see a `GET /…` trace with the SQL queries and any jobs nested under
it, plus request metrics and your logs — all exported to `endpoint`.

For local development, set `exporter` to `console` to print spans/metrics/logs to stdout — no collector
needed.

## New to observability? A hands-on tour

Never instrumented an app before? Start here — you'll see real output in two minutes, no servers to
install.

### The three pillars, in plain words

Observability answers "what is my app doing, and why is it slow or broken?" with three kinds of data:

- **Logs** — *what happened*, as text events: "order received", "payment failed". You already know these.
- **Metrics** — *how much / how often*, as numbers you graph over time: requests per second, error rate,
  p95 latency, orders placed.
- **Traces** — *where the time went* for one request, as a tree of timed steps: "this `POST /orders`
  took 40ms; 6ms of it was one SQL query." A trace is built from **spans** (one timed operation each);
  spans nest to form the tree.

You don't pick one — they work together, and arvel wires all three from a single switch.

### See it locally (no Grafana needed)

Turn telemetry on with the **console** exporter, which just prints to your terminal:

```python
# config/telemetry.py
config = {"enabled": True, "exporter": "console"}
```

Now write a route that does what a real one would — log something, touch the database, and count a
business event:

```python
# routes/web.py
from arvel import Log, Route
from arvel.telemetry import meter

async def place_order(request):
    Log.info("order received", customer="ada", total=4200)            # a log
    await Order.create(customer="ada", total=4200)                    # a DB write (auto-traced)
    meter().create_counter("orders.placed").add(1, {"plan": "pro"})   # a metric
    return {"status": "placed"}

Route.post("/orders", place_order)
```

Run `arvel serve` and `curl -X POST localhost:8000/orders`. Three kinds of output print — trimmed here
to the parts that matter:

**A trace** — the request, with the DB write nested inside it. Note both share one `trace_id`, and the
query's `parent_id` points at the request span:

```jsonc
{ "name": "POST /orders", "kind": "SERVER",
  "trace_id": "0x5508…b227", "span_id": "0xa907…c81b", "parent_id": null,
  "attributes": { "http.request.method": "POST", "http.response.status_code": 200 } }

{ "name": "db INSERT", "kind": "CLIENT",
  "trace_id": "0x5508…b227", "span_id": "0x1f93…",  "parent_id": "0xa907…c81b",  // ← child of the request
  "attributes": { "db.system": "sqlite",
                  "db.statement": "INSERT INTO orders (customer, total) VALUES (?, ?)" } }  // ← placeholders, never the values
```

That tree — request on top, query underneath — *is* a trace. In a UI like Grafana you'd see them as
nested bars on a timeline, so a slow query is obvious at a glance.

**A log** — your `Log.info` line, carrying the **same `trace_id`** as the request, so the log is linked
to the trace it happened in (click a span → see its logs):

```jsonc
{ "body": "order received", "severity_text": "INFO",
  "attributes": { "customer": "ada", "total": 4200 },
  "trace_id": "0x5508…b227", "span_id": "0xa907…c81b" }   // ← same trace as above
```

**A metric** — the counter you incremented, a number you can chart and alert on later:

```jsonc
{ "name": "orders.placed", "data_points": [ { "attributes": { "plan": "pro" }, "value": 1 } ] }
```

That's the whole idea: one request produced a **trace** (where time went), a **log** (what happened,
linked to that trace), and a **metric** (a number to chart) — and you wrote almost no telemetry code.
The request span and the DB span appeared on their own; the log and the metric were one line each.

### Next: real dashboards

`console` is just for seeing it work. In production you switch `exporter` to `otlp` and point `endpoint`
at a collector, and the same data flows into **Grafana** — traces in Tempo, metrics in Mimir, logs in
Loki — where you get searchable traces, dashboards, and alerts (see [Sending to Grafana](#sending-to-grafana)).
The code above doesn't change; only the config does.

## Configuration

All keys live under `config/telemetry.py` (a typed view, `TelemetrySettings`):

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `False` | Master switch. Off → a complete no-op (no OTel import). |
| `service_name` | `"arvel"` | `service.name` on every span/metric/log (how the service shows in the backend). |
| `exporter` | `"otlp"` | Exporter for traces/logs (and push metrics): `otlp` (prod), `console` (dev), `memory` (tests). |
| `endpoint` | `""` | OTLP/HTTP **traces** URL, e.g. `http://collector:4318/v1/traces`. The `/v1/metrics` and `/v1/logs` paths are derived from it. |
| `traces` | `True` | Toggle the traces signal. |
| `metrics` | `True` | Toggle the metrics signal. |
| `logs` | `True` | Toggle the logs signal. |
| `prometheus` | `False` | Metrics delivery: `False` = OTLP push; `True` = expose a Prometheus `/metrics` scrape route. |
| `sentry_dsn` | `""` | If set, also initialize Sentry for error reporting. |

Each signal is independent — e.g. traces + logs but not metrics:

```python
config = {"enabled": True, "endpoint": "...", "metrics": False}
```

## Traces

### Automatic

When telemetry is on, arvel traces the request lifecycle with **no code**:

- **HTTP requests** → a `SERVER` span `GET /orders` (method, path, status; 5xx/exception → error). It
  honors incoming W3C `traceparent` headers, so a request is one distributed trace across services.
- **Database queries** → a `CLIENT` span `db SELECT` per query (with `db.system` and the SQL text),
  nested under the request.
- **Cache operations** → a `CLIENT` span `cache get`/`cache put`/… (`get` records `cache.hit`).
- **Outbound HTTP** (the `Http` client) → a `CLIENT` span `HTTP GET` that **injects the W3C
  `traceparent`** into the outgoing request, so the called service continues the same trace.
- **Queue jobs** → a `CONSUMER` span `job SendWelcome` around each job's execution. The dispatching
  trace context rides in the job payload, so even a job run by a **separate worker process** links back
  to the request that queued it.

A single request trace therefore looks like:

```
GET /orders                       (SERVER, 38ms)
├─ db SELECT                      (CLIENT, 6ms)   SELECT * FROM orders WHERE user_id = ?
├─ db SELECT                      (CLIENT, 4ms)   SELECT * FROM users WHERE id = ?
└─ job SendReceipt               (CONSUMER, 2ms)  (when dispatched inline)
```

### Manual spans

For finer detail inside a handler, job, or command, use `tracer()` — a standard OpenTelemetry tracer.
Its spans nest under the active span automatically:

```python
from arvel import Route
from arvel.telemetry import tracer

async def checkout(request):
    with tracer().start_as_current_span("checkout") as span:
        span.set_attribute("order.id", 42)
        await charge_card()          # any db spans here nest under "checkout"
    return {"ok": True}

Route.post("/checkout", checkout)
```

## Metrics

### Automatic

Every HTTP request records two instruments, tagged with method + status:

- `http.server.request.count` — a counter
- `http.server.request.duration` — a histogram (seconds)

```promql
# requests/sec by status, and p95 latency
rate(http_server_request_count_total[1m])
histogram_quantile(0.95, rate(http_server_request_duration_seconds_bucket[5m]))
```

### Manual metrics

Use `meter()` for your own counters, histograms, and gauges:

```python
from arvel.telemetry import meter

orders = meter().create_counter("orders.placed", unit="{order}")
orders.add(1, {"plan": "pro"})

cart = meter().create_histogram("cart.value", unit="USD")
cart.record(79.90, {"currency": "USD"})
```

## Logs

arvel's own `Log` is exported over OTLP (to Grafana Loki, …) **with trace context attached** — every
log line is linked to the trace and span it happened in, so you can jump from a span in Tempo to its
logs. Bound fields ride along as log attributes. Just log as usual:

```python
from arvel import Log

Log.info("checkout complete", order_id=order.id, total=order.total)
```

Standard-library `logging` is exported too. Your normal console/JSON log output on stdout is unchanged —
OTLP export is additional. (This bridges arvel's structlog pipeline into OpenTelemetry.)

## Delivery: push vs pull

Metrics can reach your backend two ways.

**Push (default)** — the app sends metrics over OTLP to a collector. No inbound endpoint; works through
egress. Nothing to do beyond `endpoint`.

**Pull (Prometheus)** — set `prometheus: true` and arvel exposes a `/metrics` scrape endpoint in the
Prometheus exposition format (traces/logs still push over OTLP):

```python
# config/telemetry.py  →  enable scraping
config = {"enabled": True, "prometheus": True}
```

```yaml
# prometheus.yml
scrape_configs:
  - job_name: blog
    static_configs:
      - targets: ["blog:8000"]   # scrapes http://blog:8000/metrics
```

```bash
curl localhost:8000/metrics
# # TYPE http_server_request_count_total counter
# http_server_request_count_total{http_request_method="GET",http_response_status_code="200"} 12.0
```

> The `/metrics` route is unauthenticated by default — firewall it to your monitoring network or front
> it with auth.

## Sending to Grafana

Run a collector that accepts OTLP and fans out to Grafana's stores, then point `endpoint` at it:

```
                              ┌─▶ Tempo  (traces)  ┐
your app ─OTLP/HTTP─▶ Alloy / ─┼─▶ Mimir  (metrics) ┼─▶ Grafana
            Collector         └─▶ Loki   (logs)    ┘
```

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=blog
OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318/v1/traces
```

You set the **traces** endpoint; arvel derives the sibling `/v1/metrics` and `/v1/logs` paths. Any
OTLP-compatible pipeline (Jaeger, Honeycomb, Datadog's OTLP intake, …) works the same way — swap the
endpoint. For Prometheus-pull metrics, use [push vs pull](#delivery-push-vs-pull) above instead.

## Errors → Sentry

Set `sentry_dsn` (needs `sentry-sdk`, in the `[telemetry]` extra) and arvel initializes Sentry at boot
for error reporting, alongside OTLP tracing:

```python
config = {"enabled": True, "endpoint": "...", "sentry_dsn": env("SENTRY_DSN", "")}
```

## Security

- **No SQL values in traces.** Database spans record the statement with **placeholders only**
  (`WHERE id = ?`) — bind parameter *values* are never put in span attributes, so confidential data
  doesn't leak to your telemetry backend.
- **`/metrics` is open by default.** In pull mode, restrict the endpoint to your monitoring network or
  add auth in front of it.
- **OTLP endpoint trust.** Point `endpoint` at a collector you control; telemetry can include request
  metadata.

## Common mistakes & gotchas

- **Forgetting the extra.** Telemetry needs `arvel[telemetry]`; without it, enabling it raises an import
  error for `opentelemetry`.
- **Wrong OTLP path.** The HTTP exporter wants the full traces path — `http://host:4318/v1/traces`, not
  just `http://host:4318`.
- **Expecting spans while disabled.** `tracer()`/`meter()` always return objects, but with telemetry off
  they're no-ops (nothing is exported). Turn on `enabled`.
- **Auto-instrumentation scope.** HTTP requests, DB queries, cache operations, outbound HTTP, and queue
  jobs are auto-traced. For anything else, wrap it with `tracer()` (or the `span()` helper) where you
  want detail.
- **Prometheus vs push.** `prometheus: true` changes only *metrics* delivery; traces and logs still push
  over OTLP via `endpoint`.

## See also

- [Queues & Jobs](queues.md) — the jobs that show up as `job …` spans.
- [Database & ORM](database/index.md) — the queries that show up as `db …` spans.
- [Packaging & Extras](packaging.md) — what the `[telemetry]` extra installs.
