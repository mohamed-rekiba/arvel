# Logging

Arvel builds on **structlog** with a small **facade** that feels close to Laravel’s `Log` helper: named loggers, channels, bound context, and structured key/value fields. Third-party libraries that still use stdlib `logging` get bridged through the same processors, so your JSON or console output stays consistent.

## The `Log` facade

`Log` is a prebuilt `LoggerFacade` rooted at the `arvel` logger name. Use it anywhere you would call `logger.info(...)` in another framework—except every call takes an **event** string plus structured fields.

```python
from arvel.logging import Log

logger = Log.named("myapp.orders")

logger.info("order_placed", order_id="01J...", amount_cents=999)
```

## `LoggerFacade` methods

- `named(name)` — structlog logger for a dotted path
- `channel(name)` — logger bound to a configured channel (see below)
- `with_context(**fields)` — return a new facade with default fields merged in
- `debug`, `info`, `warning`, `error`, `critical`, `exception` — emit events with optional positional formatting guarded by Arvel’s safe bound logger

```python
from arvel.logging import Log

pay_log = Log.with_context(feature="payments")
pay_log.warning("card_declined", reason="insufficient_funds", user_id=42)
```

## Configuration pipeline

Observability settings drive `configure_logging` in `arvel.observability.logging`. It:

- Selects JSON vs console rendering (with sensible auto defaults by environment)
- Adds processors for log level, logger name, ISO timestamps, flattening noisy multiline events
- Merges **context** from Arvel’s `Context` store into every event (request ids, tenant ids, anything your providers stash)
- Applies **redaction** patterns so keys matching configured substrings become `***`
- Optionally wires per-channel file handlers (`single`, `daily`) under `arvel.logging.<channel>`

Tune log level, format, color mode, retention, and redaction lists through your observability config—not by editing call sites.

## Channels

`configure_channels(default_channel=..., channels={...})` defines named sinks (`stderr`, `single`, `daily`) used by `LoggerFacade.channel`. The registry rejects unknown channel names early so a typo fails fast during boot instead of silently dropping logs.

## Request-scoped context

Use `bind_log_context`, `scoped_log_context`, `unbind_log_context`, and `clear_log_context` from `arvel.logging` to attach identifiers around middleware boundaries. Pair this with `Context` (merged automatically by the logging processors) so every line carries correlation data without repeating kwargs on each call.

```python
from arvel.logging import scoped_log_context, Log

with scoped_log_context(request_id="abc-123"):
    Log.info("handler_enter", route="users.show")
```

## When to log what

- **Info**: business milestones (job dispatched, payment captured)
- **Warning**: recoverable anomalies (retry, fallback, validation failures you handle)
- **Error / exception**: unexpected failures—pass `exc_info` implicitly via `exception()` when inside an `except` block

Keep secrets out of fields; rely on redaction patterns for defense in depth, but never log tokens or passwords intentionally.

## Framework alignment

Because Arvel targets async I/O, structured logging matters: grep-friendly JSON in production, human-readable console in development. The same `Log` import works in application code, service providers, and validation rules—stay consistent and your operators will thank you.
