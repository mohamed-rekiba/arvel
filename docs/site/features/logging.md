# Logging

<a name="introduction"></a>
## Introduction

To help you learn more about what's happening within your application, Arvel provides logging through the `Log` facade. Logging is **structured** and **OpenTelemetry-backed**: every message carries a name plus arbitrary key/value context, and flows into the OTel pipeline alongside your traces and metrics.

The observability subsystem is **auto-registered** — `Log` works out of the box, no provider to add.

<a name="quick-start"></a>
### Quick start

```python
from arvel.facades import Log

Log.info("user.created", user_id=42)
Log.warning("rate.limited", ip="203.0.113.5")

try:
    await charge(card)
except PaymentError as e:
    Log.error("charge.failed", exc=e, amount=99)
```

Module-scoped logger (idiomatic across the framework):

```python
from arvel.facades import Log

logger = Log.channel(__name__)
logger.info("order.placed", order_id=order.id)
```

> [!NOTE]
> `Log` is the same object whether you import from `arvel.facades` or `arvel.logging`. See [Facades](../core-concepts/facades.md#the-arvel-facades-package).

<a name="writing-log-messages"></a>
## Writing Log Messages

The first argument is a short, machine-friendly message name; everything else is keyword context:

```python
from arvel.facades import Log

Log.info("user.created", user_id=42)
Log.warning("rate.limited", ip="203.0.113.5")
```

<a name="log-levels"></a>
### Log Levels

| Method | When to use |
|---|---|
| `Log.debug(message, **context)` | Diagnostic detail for development |
| `Log.info(message, **context)` | Normal, noteworthy events |
| `Log.warning(message, **context)` | Something unexpected but recoverable |
| `Log.error(message, *, exc=None, **context)` | A failure; pass the exception via `exc=` |
| `Log.critical(message, **context)` | A failure demanding immediate attention |

`error` takes a keyword-only `exc` so the exception and stack are captured:

```python
try:
    await charge(card)
except PaymentError as e:
    Log.error("charge.failed", exc=e, amount=99)
```

<a name="structured-context"></a>
### Structured Context

Pass any keyword arguments and they become structured fields on the log record — no string interpolation. This keeps logs queryable:

```python
Log.info("order.placed", order_id=order.id, total=order.total, currency="USD")
```

<a name="contextual-information"></a>
## Contextual Information

Sometimes you want every log line in a unit of work to share the same fields. `with_context` returns a child logger with those fields bound:

```python
log = Log.with_context(request_id="abc123")
log.info("request.received")
log.warning("rate.limited")   # both carry request_id=abc123
```

<a name="channels"></a>
## Channels

`channel(name)` returns a logger that uses `name` as its OpenTelemetry instrumentation scope — a clean way to attribute logs to a module:

```python
logger = Log.channel("payments")
logger.error("charge.failed", amount=99)
```

This is the idiomatic module-level pattern across the framework:

```python
from arvel.facades import Log

logger = Log.channel(__name__)
```

<a name="redacting-secrets"></a>
## Redacting Secrets

Context fields whose names look like credentials are replaced with `[REDACTED]` before a record is emitted, so secrets never land in your logs. Matching is by **substring** — a hint like `token` also redacts `access_token`, `refresh_token`, and the like:

```python
Log.info("oauth.exchange", access_token="...", user_id=7)
# -> access_token=[REDACTED], user_id=7
```

The default hints are `password`, `token`, `secret`, `authorization`, `api_key`, and `private_key`. Override them with the `LOG_REDACT_FIELDS` env var (comma-separated):

```dotenv
LOG_REDACT_FIELDS=password,token,secret,pin,ssn
```

Redaction recurses — it reaches secret-named keys nested in dicts and lists at any depth, so passing a whole payload as one field is still safe:

```python
Log.info("login", payload={"password": "...", "user": "alice"})
# -> payload={'password': '[REDACTED]', 'user': 'alice'}
```

Exception text captured via `exc=` (the message and stack trace) is logged as-is — it isn't key/value context, so keep secrets out of exception messages.

<a name="configuration"></a>
## Configuration

Logging is configured through `ObservabilityConfig` (the `OTEL_*` environment variables), shared with tracing and metrics. The `ObservabilityServiceProvider` is auto-registered and mounts the `ObservabilityMiddleware`, so request context is attached to logs automatically.
