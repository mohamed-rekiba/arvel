# Health Checks

Deploy pipelines and orchestrators need a binary signal: **is this process safe to receive traffic?** Arvel exposes a **`HealthRegistry`**, a **`HealthCheck`** protocol, **`HealthStatus`** (`healthy`, `degraded`, `unhealthy`), and typed payloads for HTTP responses—plus CLI **`arvel health check`** for quick probes from your laptop or jump host.

At **v0.1.0**, integrate with **OpenTelemetry** and **Sentry** separately (see tracing and error reporting docs); health checks focus on **synthetic dependency tests**, not full APM.

## Registering checks

Implement **`HealthCheck`**: a **`name`** attribute and async **`check() -> HealthResult`**. Register instances on **`HealthRegistry`**; **`run_all`** executes each check with a **timeout**, marking slow checks as **degraded** rather than hanging forever.

```python
import time

from arvel.observability.health import HealthCheck, HealthRegistry, HealthResult, HealthStatus


class DatabaseHealth:
    name = "database"

    async def check(self) -> HealthResult:
        start = time.monotonic()
        try:
            # await a lightweight SELECT 1 or ping
            ...
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=str(exc),
                duration_ms=elapsed,
            )
        elapsed = (time.monotonic() - start) * 1000
        return HealthResult(
            status=HealthStatus.HEALTHY,
            message="ok",
            duration_ms=elapsed,
        )


registry = HealthRegistry(timeout=5.0)
registry.register(DatabaseHealth())
payload = await registry.run_all()
```

**`HealthEndpointPayload`** aggregates overall status and per-check rows—ideal for **`GET /health`** JSON responses.

## CLI probes

**`arvel health check`** pings **database**, **cache**, and **queue** connectivity using your configured settings, printing a small table and exiting non-zero on failure—perfect in **`deploy.sh`** before flipping a load balancer.

## Degraded vs unhealthy

Reserve **unhealthy** for “this instance cannot serve correct traffic.” Use **degraded** when a **non-critical dependency** is slow or flaky (for example a metrics sidecar) but core user journeys still succeed—callers can decide whether to drain the pod.

## Framework integration checks

**`arvel.observability.integration_health`** ships ready-made probes (database, cache, queue, storage) that mirror what the CLI exercises—import classes like **`DatabaseHealthCheck`** when you want parity between **`arvel health check`** and your HTTP **`/health`** route. Keep custom checks **fast** and **idempotent**; endpoints are polled **often**.

Health checks are the contract between **your app and the platform**: honest signals, tight timeouts, and structured results so on-call engineers see **what broke** without opening five dashboards first.
