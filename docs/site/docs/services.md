# Services & Health

Arvel gives long-lived resources — database pools, cache clients, message brokers — a
single managed lifecycle through `BaseService`. Register a service once and the framework
connects it on boot, disconnects it on shutdown, and folds its health into `/_health`.

## The `BaseService` contract

```python
from arvel.services import BaseService, HealthResult, HealthStatus


class RedisService(BaseService):
    name = "redis"

    def __init__(self, url: str) -> None:
        self._url = url
        self._client = None

    async def connect(self) -> None:
        self._client = await aioredis.from_url(self._url)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def health_check(self) -> HealthResult:
        await self._client.ping()
        return HealthResult(HealthStatus.healthy)
```

- `connect()` runs during `Application.boot()`, in registration order. Raising here aborts
  boot with a `ServiceConnectError` naming the service.
- `disconnect()` runs during `Application.shutdown()`, in reverse order. A failing
  `disconnect()` is logged and the remaining services still tear down.
- `health_check()` is the only required method. `connect`/`disconnect` default to no-ops, so
  a probe-only service can skip them.

`HealthResult` carries a `status` (`healthy`, `degraded`, or `unhealthy`) and an optional
`detail`. Keep `detail` clean — it's served over HTTP, so never put connection strings,
credentials, or internal hostnames in it.

## Registering a service

```python
def boot(self) -> None:
    self.app.register_service(RedisService(self.config.redis_url))
```

The framework's own `DatabaseService` and `CacheService` register themselves from their
providers, so the database and cache always show up in the health report.

## The `/_health` endpoint

Every Arvel app exposes `GET /_health`. It runs all registered `health_check()` methods
**concurrently** and aggregates them:

| Condition | Status | HTTP |
|---|---|---|
| All healthy | `healthy` | 200 |
| Some degraded, none unhealthy | `degraded` | 200 |
| Any unhealthy | `unhealthy` | 503 |

```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "healthy", "detail": null},
    "cache": {"status": "healthy", "detail": null}
  }
}
```

Each check is bounded by a 5-second timeout. A check that overruns is reported as
`unhealthy` with `detail: "timeout"` rather than hanging the probe.

### Restricting access

Health data can leak topology, so `/_health` supports CIDR allow-listing. Set
`HEALTH_ALLOWED_CIDRS` to a comma-separated list:

```bash
HEALTH_ALLOWED_CIDRS=10.0.0.0/8,192.168.0.0/16
```

Requests from outside the range get `403`. An empty value (the default) allows any source —
fine when load balancers and Kubernetes probes reach the endpoint from arbitrary pod IPs.

## Graceful shutdown

Under uvicorn, `SIGTERM`/`SIGINT` triggers the ASGI lifespan shutdown, which calls
`Application.shutdown()` and every registered `disconnect()`. In-flight requests drain first.

Set the drain window with `GRACEFUL_SHUTDOWN_TIMEOUT` (seconds); `arvel serve` forwards it to
uvicorn's `timeout_graceful_shutdown`:

```bash
GRACEFUL_SHUTDOWN_TIMEOUT=30 arvel serve
```

Override `disconnect()` to roll back any open transaction so a rolling deploy never leaves
uncommitted writes behind.

## Testing

`disconnect()` ordering and health aggregation are covered by the lifecycle regression suite.
For your own services, drive `connect()`/`health_check()` directly and assert on the
`HealthResult`.
