# Logging

Arvel ships structured logging out of the box, backed by OpenTelemetry. Logs are JSON-formatted by default, so they ship cleanly to any aggregator.

## Quick start

```python
from arvel.facades import Log


Log.info("user.created", user_id=user.id, email=user.email)
Log.warning("rate_limit.hit", ip=request.client.host, route=request.url.path)
Log.error("payment.failed", order_id=order.id, provider="stripe", exc_info=True)
```

Each log call produces a JSON line:

```json
{
  "ts": "2026-05-19T01:30:00.123Z",
  "level": "info",
  "event": "user.created",
  "user_id": 42,
  "email": "alice@example.com",
  "request_id": "01HQXKZ8...",
  "service": "myapp"
}
```

## Configuration

| Env var | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `info` | Minimum level: `debug`, `info`, `warning`, `error`, `critical` |
| `LOG_FORMAT` | `json` | `json` for production, `console` for local dev |
| `LOG_REDACT_FIELDS` | see below | Comma-separated field names whose values are replaced with `[REDACTED]` |
| `LOG_UVICORN_ACCESS` | `true` | Bridge Uvicorn access logs through the OTel pipeline |
| `OTEL_SERVICE_NAME` | `APP_NAME` or `arvel` | `service` field on every log line |

For local development, `LOG_FORMAT=console` produces colorized, human-readable output. In production, leave it at `json`.

## Bound context

Every log line automatically carries:

- `request_id` — from the request-ID middleware
- `user_id` — when authenticated
- `route` — the matched route name
- `service` — your service name

You can attach extra fields for the duration of a scope with `with_context`:

```python
from arvel.facades import Log


@Route.post("/orders")
async def create(form: CreateOrder) -> dict:
    logger = Log.with_context(order_intent_id=form.validated().idempotency_key)
    # Every call through `logger` carries order_intent_id
    logger.info("order.processing")
    ...
```

## Log levels

| Level | When to use |
|---|---|
| `debug` | Diagnostic detail. Gate with `LOG_LEVEL=info` in production to suppress. |
| `info` | Notable business events: user created, order placed, payment succeeded. |
| `warning` | Recoverable issues: external service slow, retry succeeded. |
| `error` | Unexpected failures the system handled but you should know about. |
| `critical` | System health is degraded. Pages on-call. |

Validation errors, 401s, 403s, and 404s are **not** error-level — they're expected outcomes. Reserve `error` for things that suggest a bug.

## Logging exceptions

```python
try:
    await charge_card(order)
except StripeApiError as exc:
    # Pass the exception directly, or use exc_info=True to capture sys.exc_info()
    Log.error("payment.failed", order_id=order.id, exc=exc)
    raise
```

Both `exc=exc` (explicit) and `exc_info=True` (stdlib-compatible shorthand) work. The log record
will include `exception.type`, `exception.message`, and `exception.stacktrace` attributes.

For uncaught exceptions, the framework's exception handler does this automatically. See [Errors](errors.md).

## Channels (named loggers)

For separating high-volume diagnostic logs from business events:

```python
audit_log = Log.channel("audit")
audit_log.info("user.deleted", user_id=42, deleted_by=admin.id)
```

Channels share the parent's bound context and are scoped to the OTel instrumentation namespace
`arvel.<name>`. Filter or route them in your collector by instrumentation scope.

## Sensitive data

**Never log secrets.** Specifically:

- Passwords (even hashed)
- API keys, tokens, bearer credentials
- Full credit card numbers
- Health/PII data subject to compliance rules

If a field might contain sensitive data, redact it explicitly:

```python
Log.info("user.login", email=user.email, password="[REDACTED]")
```

Arvel auto-redacts fields whose key matches the `LOG_REDACT_FIELDS` list. The default list is:
`password`, `token`, `secret`, `authorization`, `api_key`, `private_key`. Override it with a
comma-separated env var:

```env
LOG_REDACT_FIELDS=password,token,secret,authorization,api_key,private_key,ssn,card_number
```

## Observability beyond logs

Logs are one of three signals. For the other two:

- **Metrics** — Prometheus exposition format is available at `/_metrics` if `OBSERVABILITY_METRICS_ENABLED=true`.
- **Tracing** — OpenTelemetry export to OTLP-compatible collectors via `OTEL_EXPORTER_OTLP_ENDPOINT`.

All three signals share the same `request_id` field for correlation.

## Where to next?

- [Errors](errors.md) — how exceptions become log entries.
- [Configuration](configuration.md) — all logging env vars.
- [Deployment](deployment.md) — production logging setup.
