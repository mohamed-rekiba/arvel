# Application Monitoring

Arvel emits structured JSON logs for every request, query, and background job. Route those logs to any observability backend.

## OpenTelemetry

```bash
uv add opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
```

Connects to Grafana Tempo, Jaeger, Honeycomb, Datadog, and any other OTLP-compatible backend.

## Sentry

```bash
uv add sentry-sdk[fastapi]
```

```python
import sentry_sdk
sentry_sdk.init(dsn="https://...", traces_sample_rate=0.1)
```

Captures exceptions, slow transactions, and queue-job errors.

## See also

- [Logging](logging.md) — structlog configuration and output channels.
- [Debugging & Observability](observability.md) — local development tools.
