# Telemetry & Observability

arvel ships first-class **OpenTelemetry** for all three signals — **traces, metrics, and logs** — and
exports them over the open **OTLP** wire format to any backend: Grafana (Tempo · Mimir · Loki), the
OpenTelemetry Collector, Jaeger, Honeycomb, Datadog, … There's no proprietary agent and no vendor
lock-in; you pick (and change) the backend in config.

It is **off by default** and costs nothing until you turn it on — `opentelemetry` is imported only when
enabled, so `import arvel` and the CLI stay light. Once on, HTTP requests, database queries, cache
operations, outbound HTTP, and queue jobs are traced automatically, request metrics are recorded, and
your `Log` output is exported and correlated to the trace it happened in.

!!! note "Needs the `[telemetry]` extra"
    Turn it on with `uv add 'arvel[telemetry]'` (the OpenTelemetry SDK + OTLP/Prometheus exporters,
    plus `sentry-sdk`) and `enabled: true` in config. Without the extra, enabling telemetry raises an
    import error for `opentelemetry`.

## Contents

- [The three pillars, in plain words](#the-three-pillars)
- [How it fits together (the mental model)](#how-it-fits-together)
- [Getting started in 5 minutes](#getting-started-in-5-minutes)
- [Configuration](#configuration)
- [Traces](#traces) — automatic spans, `span()`, `tracer()`, span kinds
- [Metrics](#metrics) — automatic + your own instruments
- [Logs](#logs) — export + trace correlation
- [Guarding expensive work](#guarding-expensive-work) — `is_tracing_enabled` / `is_metrics_enabled`
- [Testing telemetry](#testing-telemetry)
- [Programmatic setup & custom exporters](#programmatic-setup)
- [Delivery: push vs pull](#delivery-push-vs-pull)
- [Sending to Grafana](#sending-to-grafana)
- [Errors → Sentry](#errors--sentry)
- [Security](#security)
- [Common mistakes & gotchas](#common-mistakes--gotchas)
- [API reference](#api-reference)

## The three pillars {#the-three-pillars}

Never instrumented an app before? Observability answers *"what is my app doing, and why is it slow or
broken?"* with three kinds of data:

- **Logs** — *what happened*, as text events: "order received", "payment failed". You already know these.
- **Metrics** — *how much / how often*, as numbers you graph over time: requests per second, error
  rate, p95 latency, orders placed.
- **Traces** — *where the time went* for one request, as a tree of timed steps: "this `POST /orders`
  took 40ms; 6ms of it was one SQL query." A trace is built from **spans** — one span is one timed
  operation, and spans nest to form the tree.

You don't pick one — they work together, and arvel wires all three from a single switch. The magic is
**correlation**: a log line carries the `trace_id` of the request it happened in, so you can click a
slow span and jump straight to its logs.

## How it fits together {#how-it-fits-together}

You only ever touch two things: **config** (to turn it on and point it somewhere) and a couple of
**helper functions** (`span()`, `tracer()`, `meter()`) for your own instrumentation. Here's what
happens underneath, so nothing is a black box:

```
config/telemetry.py          ← you set enabled + endpoint here
        │
        ▼
TelemetryServiceProvider.boot()   ← auto-discovered at app boot
        │  calls
        ▼
arvel.telemetry.configure()   ← builds the global OTel tracer/meter/logger providers
        │                        from your exporter choice, and flips two gate flags
        ▼
  ┌─────────────┬──────────────┬───────────────┐
  │ tracer      │ meter        │ logger        │   the global OpenTelemetry providers
  │ provider    │ provider     │ provider      │
  └─────────────┴──────────────┴───────────────┘
        ▲              ▲               ▲
   span()/tracer()  meter()      arvel's Log (bridged in)
   (your spans +   (request +    (every log line, stamped
    auto spans)     your metrics)  with the active trace_id)
```

Three design choices explain almost everything about how telemetry behaves:

1. **Off by default, zero-cost when off.** `configure()` is a no-op unless `enabled: true`, and it
   never imports `opentelemetry` until then. The helpers check a cheap boolean (`is_tracing_enabled()`)
   before doing any OTel work — so a default app pays *nothing*, not even an import.
2. **Global providers.** `configure()` installs process-wide OTel providers (once). That's why
   `tracer()`/`meter()` anywhere in your code — and arvel's own auto-instrumentation — all feed the
   same pipeline without you passing anything around.
3. **Backend-agnostic over OTLP.** arvel never talks to a vendor SDK; it emits OTLP, the open standard.
   You change backends by changing `endpoint`, not code.

## Getting started in 5 minutes {#getting-started-in-5-minutes}

The fastest way to *see* telemetry is the **console** exporter — it prints to your terminal, so you
need no collector, no Grafana, nothing to install beyond the extra.

```bash
uv add 'arvel[telemetry]'
```

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

Run `arvel serve` and `curl -X POST localhost:8000/orders`. Three kinds of output print — trimmed to
the parts that matter:

**A trace** — the request, with the DB write nested inside it. Both share one `trace_id`, and the
query's `parent_id` points at the request span:

```jsonc
{ "name": "POST /orders", "kind": "SERVER",
  "trace_id": "0x5508…b227", "span_id": "0xa907…c81b", "parent_id": null,
  "attributes": { "http.request.method": "POST", "http.response.status_code": 200 } }

{ "name": "db INSERT", "kind": "CLIENT",
  "trace_id": "0x5508…b227", "span_id": "0x1f93…", "parent_id": "0xa907…c81b",  // ← child of the request
  "attributes": { "db.system": "sqlite",
                  "db.statement": "INSERT INTO orders (customer, total) VALUES (?, ?)" } }  // ← placeholders, never values
```

**A log** — your `Log.info` line, carrying the **same `trace_id`** as the request:

```jsonc
{ "body": "order received", "severity_text": "INFO",
  "attributes": { "customer": "ada", "total": 4200 },
  "trace_id": "0x5508…b227", "span_id": "0xa907…c81b" }   // ← same trace as above
```

**A metric** — the counter you incremented, a number you can chart and alert on:

```jsonc
{ "name": "orders.placed", "data_points": [ { "attributes": { "plan": "pro" }, "value": 1 } ] }
```

That's the whole idea. One request produced a **trace** (where time went), a **log** (what happened,
linked to that trace), and a **metric** (a number to chart) — and you wrote almost no telemetry code:
the request span and the DB span appeared on their own; the log and the metric were one line each. In
production you switch `exporter` to `otlp` and point `endpoint` at a collector — the code above doesn't
change, only the config does.

## Configuration {#configuration}

All keys live under `config/telemetry.py` (a typed view, `TelemetrySettings` — a typo or wrong type is
a clear boot error, not a silent miss):

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `False` | Master switch. Off → a complete no-op (no OTel import). |
| `service_name` | `"arvel"` | `service.name` on every span/metric/log (how the service shows up in the backend). |
| `exporter` | `"otlp"` | Where traces/logs (and push metrics) go: `otlp` (prod), `console` (dev — prints to stdout), `memory` (tests). |
| `endpoint` | `""` | OTLP/HTTP **traces** URL, e.g. `http://collector:4318/v1/traces`. The `/v1/metrics` and `/v1/logs` paths are **derived** from it — you set one. |
| `traces` | `True` | Toggle the traces signal. |
| `metrics` | `True` | Toggle the metrics signal. |
| `logs` | `True` | Toggle the logs signal. |
| `prometheus` | `False` | Metrics delivery: `False` = push over OTLP; `True` = expose a `/metrics` scrape route (see [push vs pull](#delivery-push-vs-pull)). |
| `sentry_dsn` | `""` | If set, also initialize Sentry for error reporting. |

Every field is env-friendly — a typical production config:

```python
# config/telemetry.py
from arvel import env

config = {
    "enabled":      env("OTEL_ENABLED", False),
    "service_name": env("OTEL_SERVICE_NAME", env("APP_NAME", "arvel")),
    "exporter":     env("OTEL_TRACES_EXPORTER", "otlp"),
    "endpoint":     env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"),
    "sentry_dsn":   env("SENTRY_DSN", ""),
}
```

Each signal is independent — e.g. traces + logs but not metrics:

```python
config = {"enabled": True, "endpoint": "...", "metrics": False}
```

## Traces {#traces}

### Automatic — you write nothing

When telemetry is on, arvel traces the request lifecycle for you:

| What | Span | Kind | Notes |
|------|------|------|-------|
| **HTTP request** | `GET /orders` | `SERVER` | method, path, status; a 5xx or exception marks the span an error. Honors an incoming W3C `traceparent`, so a request is one distributed trace across services. |
| **Database query** | `db SELECT` | `CLIENT` | one span per query, with `db.system` and the SQL text (**placeholders only** — never the bound values). |
| **Cache operation** | `cache get` / `cache put` / … | `CLIENT` | `get` records a `cache.hit` attribute. |
| **Outbound HTTP** (the `Http` client) | `HTTP GET` | `CLIENT` | **injects** the W3C `traceparent` into the outgoing request, so the called service continues the same trace. |
| **Queue job** | `job SendWelcome` | `CONSUMER` | the dispatching trace context rides in the job payload, so a job run by a **separate worker process** still links back to the request that queued it. |

A single request trace therefore looks like:

```
GET /orders                       (SERVER, 38ms)
├─ db SELECT                      (CLIENT, 6ms)   SELECT * FROM orders WHERE user_id = ?
├─ db SELECT                      (CLIENT, 4ms)   SELECT * FROM users WHERE id = ?
└─ job SendReceipt               (CONSUMER, 2ms)  (when dispatched inline)
```

For anything *else* — a call to a third-party library, an expensive computation — add your own span.
You have two ways to do it.

### `span()` — the gated helper (recommended)

`span()` is arvel's convenience wrapper. Prefer it for instrumenting your own code, because it:

- **is a no-op when telemetry is off** — it yields `None` and imports no `opentelemetry`, so leaving a
  `span()` in your code costs nothing in a default app;
- **auto-records errors** — if the block raises, the span is marked an error and the exception is
  recorded before it propagates;
- takes a **`kind`** and **`attributes`** inline.

```python
from arvel.telemetry import span

async def sync_inventory(sku: str):
    with span("inventory.sync", kind="client", attributes={"sku": sku}):
        await external_api.push(sku)      # any db/cache/http spans here nest underneath
```

`kind` is one of `internal` (default — work inside your service), `client` (an outbound call you make —
a DB query, an API request), `server` (handling an inbound request), `producer`/`consumer` (you put a
message on / take one off a queue). It's a hint your backend uses to draw and group spans; when in
doubt, leave it `internal`. The yielded value is the live span (or `None` when off), so guard
attribute-setting: `with span("x") as s: ... ; s and s.set_attribute("k", v)`.

### `tracer()` — the raw OpenTelemetry tracer

When you need the full OTel API — links, events, a span you start and end across `await`s, nested
`start_as_current_span` — use `tracer()`, a standard `opentelemetry` tracer. Its spans nest under the
active span automatically:

```python
from arvel.telemetry import tracer

async def checkout(request):
    with tracer().start_as_current_span("checkout") as span:
        span.set_attribute("order.id", 42)
        span.add_event("card.authorized")
        await charge_card()               # db spans here nest under "checkout"
    return {"ok": True}
```

The difference: `tracer()` always returns a real tracer object, so with telemetry **off** its spans are
created but exported nowhere (harmless but not free). `span()` short-circuits entirely when off. Rule
of thumb — reach for `span()`; drop to `tracer()` only when you need an OTel feature `span()` doesn't
expose.

## Metrics {#metrics}

### Automatic

Every HTTP request records two instruments, tagged with method + status:

- `http.server.request.count` — a counter
- `http.server.request.duration` — a histogram (seconds)

```promql
# requests/sec by status, and p95 latency
rate(http_server_request_count_total[1m])
histogram_quantile(0.95, rate(http_server_request_duration_seconds_bucket[5m]))
```

### Your own instruments

`meter()` returns a standard OpenTelemetry meter, so the full instrument set is available. Create an
instrument **once** (module level is fine) and record to it:

```python
from arvel.telemetry import meter

m = meter()   # or meter("billing") to namespace them

orders   = m.create_counter("orders.placed", unit="{order}")          # only goes up
in_flight = m.create_up_down_counter("jobs.in_flight")                 # goes up and down
cart     = m.create_histogram("cart.value", unit="USD")               # distribution → percentiles

orders.add(1, {"plan": "pro"})            # attributes become labels you can group/filter by
in_flight.add(1); in_flight.add(-1)
cart.record(79.90, {"currency": "USD"})
```

For a value you can only *observe* on demand (a queue depth, a pool size), register an **observable**
gauge with a callback OTel polls at export time:

```python
def queue_depth(options):
    from opentelemetry.metrics import Observation
    yield Observation(current_depth(), {"queue": "default"})

meter().create_observable_gauge("queue.depth", callbacks=[queue_depth])
```

Naming: use `dotted.lower.case` and put units in `unit=`. Keep attribute values **low-cardinality**
(a plan tier, a status) — never a user id or a raw URL, or you'll explode the number of time series.

## Logs {#logs}

arvel's own `Log` is exported over OTLP (to Grafana Loki, …) **with trace context attached** — every
log line carries the `trace_id`/`span_id` of the trace it happened in, so you can jump from a span in
Tempo to its logs. Bound fields ride along as log attributes. Just log as usual:

```python
from arvel import Log

Log.info("checkout complete", order_id=order.id, total=order.total)
```

Standard-library `logging` is exported too. Your normal console/JSON log output on stdout is
**unchanged** — OTLP export is *additional*, layered on without touching your existing pipeline.

How it works (so it's not magic): when logs are enabled, `configure()` inserts a processor into
arvel's structlog chain (`instrument_logging()`) that mirrors each event into the OTel log pipeline,
where the handler stamps the active span's ids. It re-asserts itself whenever the kernel rebuilds the
log processors, so the bridge can't be silently dropped. Nothing you call — it's wired at boot.

## Guarding expensive work {#guarding-expensive-work}

The helpers are already cheap when telemetry is off, but if *computing* a span's attributes is itself
expensive (serializing a payload, hashing a body), gate it so you don't pay for data nothing will
export:

```python
from arvel.telemetry import is_tracing_enabled, is_metrics_enabled, span

with span("render") as s:
    if s is not None and is_tracing_enabled():
        s.set_attribute("template.debug", expensive_debug_dump())   # only computed when tracing is on
```

Both `is_tracing_enabled()` and `is_metrics_enabled()` are plain boolean reads that import no
`opentelemetry` — safe to call on a hot path.

## Testing telemetry {#testing-telemetry}

You test instrumentation the same way it ships to production — through a **real exporter**, just an
in-memory one you can assert on. Pass an `InMemorySpanExporter` straight to `configure()`; because you
pass an explicit exporter, `configure()` sets up tracing **even though `enabled` is `False` in tests**:

```python
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from arvel.telemetry import configure, span

async def test_sync_inventory_is_traced():
    exporter = InMemorySpanExporter()
    result = configure(exporter=exporter)          # forces tracing on, returns the providers

    with span("inventory.sync", attributes={"sku": "ABC"}):
        ...

    result.tracer_provider.force_flush()           # flush the batch processor before asserting
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "inventory.sync" in spans
    assert spans["inventory.sync"].attributes["sku"] == "ABC"
```

The one wrinkle: `configure()` wires a **batched** processor (efficient in production), so call
`force_flush()` before reading `get_finished_spans()`. To capture arvel's **auto-instrumented** spans
(db/cache/queue) *synchronously* — without flush timing — attach your own exporter with a
`SimpleSpanProcessor` after enabling:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

configure(exporter=InMemorySpanExporter())         # enable tracing + install the global provider
exporter = InMemorySpanExporter()
trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))  # immediate, no batching

await db.fetch_all(sa.select(Widget))
db_spans = [s for s in exporter.get_finished_spans() if s.name.startswith("db ")]
assert any(s.name == "db SELECT" for s in db_spans)
```

For metrics, pass a `metric_reader` (an `InMemoryMetricReader`) instead and read
`reader.get_metrics_data()`; for logs, pass a `log_exporter` (an `InMemoryLogRecordExporter`). Each
signal has its own override — see below.

## Programmatic setup & custom exporters {#programmatic-setup}

Normally the `TelemetryServiceProvider` calls `configure()` for you at boot. Call it yourself only to
**override an exporter** — in tests (above), or to plug in an exporter arvel doesn't build:

```python
configure(
    settings=None,          # defaults to TelemetrySettings() (reads config/telemetry.py)
    exporter=my_span_exporter,        # any OTel SpanExporter → forces traces on
    metric_reader=my_metric_reader,   # any OTel MetricReader → forces metrics on
    log_exporter=my_log_exporter,     # any OTel LogRecordExporter → forces logs on
)
```

Passing an override for a signal turns that signal **on** regardless of config (that's how the test
harness enables one signal without a full config). `configure()` returns a `Telemetry` — a small
struct of the providers it built (`tracer_provider`, `meter_provider`, `logger_provider`; `None` for
any signal that's off) — or `None` when nothing was set up.

To register a **custom trace exporter kind** (say, a vendor SDK exporter) as a config option, you'd
build it here rather than through the `exporter` string, which only knows `otlp`/`console`/`memory`.

## Delivery: push vs pull {#delivery-push-vs-pull}

Metrics can reach your backend two ways.

**Push (default)** — the app sends metrics over OTLP to a collector. No inbound endpoint; works through
egress. Nothing to do beyond `endpoint`.

**Pull (Prometheus)** — set `prometheus: true` and arvel exposes a `/metrics` scrape endpoint in the
Prometheus exposition format (traces and logs still push over OTLP):

```python
# config/telemetry.py
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

The `/metrics` route is registered by the routing layer (telemetry itself never imports HTTP); the raw
payload comes from `prometheus_payload()` if you ever need to serve it yourself.

> The `/metrics` route is **unauthenticated by default** — firewall it to your monitoring network or
> front it with auth.

## Sending to Grafana {#sending-to-grafana}

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
endpoint. For Prometheus-pull metrics, use [push vs pull](#delivery-push-vs-pull) instead.

## Errors → Sentry {#errors--sentry}

Set `sentry_dsn` (needs `sentry-sdk`, in the `[telemetry]` extra) and arvel initializes Sentry at boot
for error reporting, alongside OTLP tracing:

```python
config = {"enabled": True, "endpoint": "...", "sentry_dsn": env("SENTRY_DSN", "")}
```

## Security {#security}

- **No SQL values in traces.** Database spans record the statement with **placeholders only**
  (`WHERE id = ?`) — bind parameter *values* are never put in span attributes, so confidential data
  doesn't leak to your telemetry backend. Keep the same discipline in your own spans: log an `order.id`,
  not a card number.
- **`/metrics` is open by default.** In pull mode, restrict the endpoint to your monitoring network or
  add auth in front of it.
- **OTLP endpoint trust.** Point `endpoint` at a collector *you* control; telemetry can include request
  metadata.
- **Attribute cardinality.** Don't put user ids, emails, or raw URLs in metric attributes — beyond the
  cost, it's PII sprayed across your metrics store.

## Common mistakes & gotchas {#common-mistakes--gotchas}

- **Forgetting the extra.** Telemetry needs `arvel[telemetry]`; without it, enabling it raises an import
  error for `opentelemetry`.
- **Wrong OTLP path.** The HTTP exporter wants the full traces path — `http://host:4318/v1/traces`, not
  just `http://host:4318`. arvel derives the metrics/logs paths from it, so getting this one right is
  all you need.
- **Expecting spans while disabled.** `tracer()`/`meter()` always return objects, but with telemetry
  off nothing is exported. `span()` goes further and no-ops entirely. Turn on `enabled` to actually see
  data.
- **Reading spans in a test without flushing.** `configure()` batches; call
  `result.tracer_provider.force_flush()` (or use a `SimpleSpanProcessor`) before `get_finished_spans()`.
- **`tracer()` vs `span()`.** Use `span()` for your own instrumentation (gated, auto-error). Drop to
  `tracer()` only for OTel features `span()` doesn't expose.
- **High-cardinality attributes.** A user id or raw URL as a metric label creates a time series per
  value — it will overwhelm your metrics store. Use bounded values (tier, status, route template).
- **`prometheus: true` changes only *metrics* delivery.** Traces and logs still push over OTLP via
  `endpoint`.

## API reference {#api-reference}

Everything public in `arvel.telemetry`:

| Symbol | Kind | Purpose |
|--------|------|---------|
| `span(name, *, kind="internal", attributes=None)` | context manager | Gated span around a block — no-op when tracing is off, auto-records errors. The everyday way to instrument your code. |
| `tracer(name="arvel")` | function | A raw OpenTelemetry tracer for the full span API. |
| `meter(name="arvel")` | function | A raw OpenTelemetry meter for counters/histograms/gauges. |
| `is_tracing_enabled()` | function | Cheap boolean gate — has `configure()` wired tracing? Imports no OTel. |
| `is_metrics_enabled()` | function | Cheap boolean gate for metrics. |
| `prometheus_payload()` | function | `(bytes, content_type)` of the current metrics in Prometheus exposition format (the `/metrics` route uses this). |
| `configure(settings=None, *, exporter=None, metric_reader=None, log_exporter=None)` | function | Set up the global providers from config; pass an override to force a signal on (tests / custom exporters). Returns `Telemetry` or `None`. |
| `TelemetrySettings` | class | Typed view over `config/telemetry.py` (see [Configuration](#configuration)). |
| `Telemetry` | dataclass | The providers `configure()` built: `tracer_provider`, `meter_provider`, `logger_provider` (`None` per off signal). |

## See also

- [Logging](logging.md) — arvel's `Log`, the request/queue log correlation exported here.
- [Queues & Jobs](queues.md) — the jobs that show up as `job …` spans.
- [Database & ORM](database/index.md) — the queries that show up as `db …` spans.
- [Packaging & Extras](packages/development.md) — what the `[telemetry]` extra installs.
