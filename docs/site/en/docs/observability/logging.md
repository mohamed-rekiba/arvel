# Structured Logging

Logs are not an afterthought—they are how you reconstruct incidents, prove compliance, and debug race conditions under load. Arvel configures **`structlog`** with opinionated processors: context variables, request IDs, optional **redaction**, and channel-aware handlers (console, single file, daily rotation) driven by **`ObservabilitySettings`**.

Call **`configure_logging`** during application bootstrap so workers, the HTTP stack, and CLI share the same pipeline.

## Why structlog

Structured logs are **machine-parseable**: JSON or key-value lines feed ELK, Loki, or CloudWatch without fragile regex. **`structlog`** binds dictionaries to log events, merges context (user id, request id, queue job name), and renders through plain **`logging`** handlers for compatibility with hosting platforms.

```python
import structlog

logger = structlog.get_logger(__name__)


async def handle_request() -> None:
    logger.info("order.created", order_id=42, amount_cents=999)
```

## Configuration highlights

**`configure_logging`** (see `arvel.observability.logging`) wires:

- **Log level** and **per-channel overrides** (`log_channel_levels`)
- **Color** behavior that respects CI and production (`log_color_mode`, `log_color_disable_in_ci`)
- **File paths** for `single` and `daily` drivers, resolved safely under your app root
- Processors such as **`RequestIdProcessor`**, **`ContextProcessor`**, and **`RedactProcessor`** for sensitive keys

Environment-specific toggles live on **`ObservabilitySettings`**—prefix and field names follow your project’s config module.

## Request correlation

Pair logging with **`RequestIdMiddleware`** and **`get_request_id`** so every line for a request shares an id—critical when you trace a 500 across services.

## Laravel comparison

If you are used to Laravel’s `Log::withContext()` and Monolog channels, think of structlog’s **contextvars** and **processors** as the same idea: **attach context once**, emit many events, ship them through pluggable sinks.

## What not to log

Passwords, tokens, full credit card numbers, and raw JWTs belong **nowhere** in logs. Use **redaction** processors and structured fields that reference opaque ids instead.

Good logging is **quiet by default, loud on failure, and always correlated**. Arvel’s observability package aims to get you there without turning every `print` into a production incident.

## OpenTelemetry tracing

Call **`configure_tracing`** from `arvel.observability.tracing` during startup to export spans to your collector—latency breakdowns complement logs when you debug slow queries or downstream HTTP calls. Use **`get_tracer`** to create spans inside services and queue jobs.

## Sentry

**`configure_sentry`** wires the Sentry SDK with framework-aware defaults so unhandled exceptions become issues with breadcrumbs from logging and request context—set your DSN via settings and keep sampling sensible in high-traffic environments.

Together—**structlog**, **OTEL**, **Sentry**, and **health checks**—form the observability stack Arvel expects in production: **narrative logs**, **trace graphs**, **error triage**, and **probe endpoints** each do one job well.
