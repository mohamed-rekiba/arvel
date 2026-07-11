# Logging

arvel logs are **structured** — every line is an *event name* plus a set of key/value fields, not a
formatted sentence. That's what lets the same log read cleanly in your terminal during development
and parse as JSON in production. It's a [structlog](https://www.structlog.org) pipeline behind the
`Log` facade; you never configure structlog yourself.

```python
from arvel import Log

Log.info("order.paid", order_id=order.id, total=order.total)
```

```text
2026-07-11T19:20:03.114Z [info     ] order.paid   order_id=42 total=4200      # dev (console)
{"event": "order.paid", "order_id": 42, "total": 4200, "level": "info", "timestamp": "…"}  # prod
```

## Event name vs. structured context

The **first argument is the event name** — a short, stable, low-cardinality string you'll search
and group by (`"order.paid"`, `"user.login.failed"`). **Everything else is keyword context** — the
structured fields.

```python
Log.info("cart.checkout", user_id=user.id, items=len(cart), total=cart.total)
```

Don't pass an object as the event — it gets stringified into the message, so you lose the fields:

```python
user = await User.first()

Log.info(user)                        # ⚠ event becomes the model's repr string
# {"event": "User(id=1, name='Super Admin', …)", "level": "info", …}

Log.info("user.loaded", user=user.to_dict())    # ✓ fields land under `user`
# {"event": "user.loaded", "user": {"id": 1, "name": "Super Admin", …}, "level": "info", …}
```

Context values must be serializable — a raw `Model` isn't, so convert it with
[`.to_dict()`](database/casts.md). This is the single most common logging mistake — and `.to_dict()`
also honors the model's `__hidden__`, so fields like `password` are dropped, whereas the raw `repr`
would leak them straight into the log.

## Levels

Five levels, lowest to highest — same signature on each:

```python
Log.debug("cache.miss", key=key)          # diagnostic; usually filtered out in prod
Log.info("order.paid", order_id=42)        # normal, expected events
Log.warning("rate_limit.near", pct=92)     # something to keep an eye on
Log.error("payment.failed", order_id=42)   # a failure that needs attention
Log.critical("db.unreachable", host=dsn)   # the app can't function
```

To pin a specific *exception type* to a quieter level when it's reported, that's the exception
handler's `level()` — see [Error Handling](errors.md#log-levels).

## Adding context

**Per-logger** — `bind()` returns a new logger that carries the given fields on every call, handy
for a unit of work:

```python
log = Log.bind(request_id=rid, user_id=user.id)
log.info("checkout.start")                 # both fields ride along
log.info("checkout.done", total=total)     # …and here
```

**Ambient (request/task-wide)** — `with_context()` binds fields into the current async context, so
**every** subsequent log event in this request/task carries them without threading a logger through.
Backed by `contextvars`, so concurrent requests never bleed into each other. Clear it when the unit
of work ends:

```python
Log.with_context(request_id=rid, tenant=tenant.slug)
# … any code here logs request_id + tenant automatically …
Log.clear_context()                        # typically at the end of the request
```

**Named channels** — `channel()` tags lines with a `channel` field to separate concerns (audit,
billing, …) when you filter downstream:

```python
Log.channel("billing").info("invoice.sent", invoice_id=inv.id)
# {"event": "invoice.sent", "channel": "billing", "invoice_id": …, …}
```

## The `logger()` / `info()` helpers

Two global shorthands (see [Helpers](helpers.md)) resolve the same facade:

```python
from arvel import logger, info

logger().info("order.paid", order_id=42)   # logger() → the Log facade, to chain on
info("order.paid", order_id=42)            # info() → the info-level shortcut
```

## Console vs. JSON output

The renderer is chosen once at boot from the environment:

- `app.env == "production"` → **JSON** (one object per line, for log aggregators).
- otherwise → the **pretty console** renderer (colorized `event  key=value`), for local dev.

So an unqualified `arvel tinker` / local run prints the readable format; set `APP_ENV=production`
(or call `configure_logging(json_logs=True)` yourself) to force JSON. In JSON mode an exception's
`exc_info` is rendered as **structured frames** (a machine-parseable `exception` field), and frame
**locals are excluded** — they routinely hold request data, passwords, and tokens, which must never
reach the logs.

## Secrets never go in logs

Structured context is convenient, which makes it easy to log too much. Never put passwords, tokens,
API keys, or full request bodies into log context. Log identifiers (`user_id`), not credentials.

## How it works

`Log` is a [facade](facades.md) over the `"log"` binding — a `LogManager` (implementing
`contracts.Logger`) registered as a container singleton at boot, wrapping a structlog logger.
`Log.info(...)` forwards to it; `bind`/`channel` return new wrapped loggers, while
`with_context`/`clear_context` drive structlog's `contextvars`. `import arvel` stays light — the
logger is built lazily through the container, never on import.

## See also

- [Helpers & Collections](helpers.md) — the `logger()` / `info()` shorthands.
- [Error Handling](errors.md) — how uncaught exceptions are reported and levelled.
- [Telemetry](telemetry.md) — logs exported over OTLP with the active trace context attached.
- [Context](context.md) — the same `contextvars` mechanism for non-logging ambient state.
