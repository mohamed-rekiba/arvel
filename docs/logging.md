# Logging

To help you learn more about what's happening within your application, arvel provides robust logging
services that let you log messages to files, the system error log, and even structured aggregators.
arvel logs are **structured** — every line is an *event name* plus a set of key/value fields, not a
formatted sentence — so the same log reads cleanly in your terminal during development and parses as
JSON in production. It's a [structlog](https://www.structlog.org) pipeline behind the `Log` facade;
you never configure structlog yourself.

```python
from arvel import Log

Log.info("order.paid", order_id=order.id, total=order.total)
```

```text
2026-07-11T19:20:03.114Z [info     ] order.paid   order_id=42 total=4200      # dev (console)
{"event": "order.paid", "order_id": 42, "total": 4200, "level": "info", "timestamp": "…"}  # prod
```

## Configuration

The output renderer is chosen once at boot from the environment:

- `app.env == "production"` → **JSON** (one object per line, for log aggregators).
- otherwise → the **pretty console** renderer (colorized `event  key=value`), for local dev.

So a local run prints the readable format; set `APP_ENV=production` (or call
`configure_logging(json_logs=True)` yourself) to force JSON. In JSON mode an exception's `exc_info` is
rendered as **structured frames** (a machine-parseable `exception` field), and frame **locals are
excluded** — they routinely hold request data, passwords, and tokens, which must never reach the logs.

## Writing log messages

Five levels, lowest to highest — same signature on each:

```python
Log.debug("cache.miss", key=key)          # diagnostic; usually filtered out in prod
Log.info("order.paid", order_id=42)        # normal, expected events
Log.warning("rate_limit.near", pct=92)     # something to keep an eye on
Log.error("payment.failed", order_id=42)   # a failure that needs attention
Log.critical("db.unreachable", host=dsn)   # the app can't function
```

The **first argument is the event name** — a short, stable, low-cardinality string you'll search and
group by (`"order.paid"`, `"user.login.failed"`). **Everything else is keyword context** — the
structured fields. Don't pass an object as the event — it gets stringified and you lose the fields:

```python
Log.info(user)                                  # ⚠ event becomes the model's repr string
Log.info("user.loaded", user=user.to_dict())    # ✓ fields land under `user`
```

Context values must be serializable — a raw `Model` isn't, so convert it with
[`.to_dict()`](database/casts.md), which also honors `__hidden__` so fields like `password` never
leak into the log.

Two global shorthands (see [Helpers](helpers.md)) resolve the same facade:

```python
from arvel import logger, info

logger().info("order.paid", order_id=42)   # logger() → the Log facade, to chain on
info("order.paid", order_id=42)            # info() → the info-level shortcut
```

## Contextual information

**Per-logger** — `bind()` returns a new logger that carries the given fields on every call, handy for
a unit of work:

```python
log = Log.bind(request_id=rid, user_id=user.id)
log.info("checkout.start")                 # both fields ride along
log.info("checkout.done", total=total)     # …and here
```

**Ambient (request/task-wide)** — `with_context()` binds fields into the current async context, so
**every** subsequent log event in this request/task carries them without threading a logger through.
Backed by `contextvars`, so concurrent requests never bleed into each other:

```python
Log.with_context(request_id=rid, tenant=tenant.slug)
# … any code here logs request_id + tenant automatically …
Log.clear_context()                        # typically at the end of the request
```

**Scoped (a block / one unit of work)** — `bound_context()` is a context manager that binds fields
for the duration of a `with` block and **restores the prior context on exit** — so it nests cleanly
and never clobbers surrounding context (unlike `with_context`/`clear_context`, which set/wipe
globally):

```python
with Log.bound_context(job_id=job_id):
    # every log line in here carries job_id; anything already bound (e.g. request_id) survives
    ...
# job_id is gone again here
```

### Request & queue correlation

Two things are wired for you:

- **HTTP** — `RequestContextMiddleware` binds a `request_id` (a `uuidv7`, or an incoming
  `X-Request-ID`) for every request, so all of a request's log lines share it.
- **Queue** — when you dispatch a job, the request's **entire bound log context** (its `request_id`
  plus anything else you bound — `user_id`, `tenant_id`, …) is captured and rides the job across the
  broker. On the worker the job re-binds all of it, **plus its own fresh `job_id` (a `uuidv7`)**. So
  a job's logs carry the same context as the request that dispatched it, and you can trace one API
  request to every queue job it spawned:

  ```
  {"event": "checkout.start", "request_id": "018f…", "user_id": 42}          # in the request
  {"event": "SendReceipt.handled", "request_id": "018f…", "user_id": 42, "job_id": "018f…"}  # in the job
  ```

  Bound values are coerced JSON-safe before they ride the broker, so keep them small identifiers.

To pin a specific *exception type* to a quieter level when it's reported, use the exception handler's
`level()` — see [Error Handling](errors.md#exception-log-levels).

## Writing to specific channels

`channel()` tags lines with a `channel` field to separate concerns (audit, billing, …) so you can
filter them downstream:

```python
Log.channel("billing").info("invoice.sent", invoice_id=inv.id)
# {"event": "invoice.sent", "channel": "billing", "invoice_id": …, …}
```

!!! warning "Secrets never go in logs"
    Structured context makes it easy to log too much. Never put passwords, tokens, API keys, or full
    request bodies into log context. Log identifiers (`user_id`), not credentials.

## See also

- [Helpers](helpers.md) — the `logger()` / `info()` shorthands.
- [Error Handling](errors.md) — how uncaught exceptions are reported and levelled.
- [Telemetry](telemetry.md) — logs exported over OTLP with the active trace context attached.
- [Context](context.md) — the same `contextvars` mechanism for non-logging ambient state.
