# Rate Limiting

Rate limiting protects your application from abuse, accidental hammering, and runaway scripts. Arvel ships a `Throttle` middleware and a `RateLimiter` facade — both backed by a pluggable store (in-memory, Redis, database).

## The `Throttle` middleware

The simplest case — limit a route or group to N requests per minute, keyed by client IP:

```python
from arvel.http.middleware import Throttle
from arvel.support import InMemoryStore


with Route.group(middleware=[Throttle(60, store=InMemoryStore())]):
    @Route.get("/api/users")
    async def list_users(): ...
```

When a client exceeds the limit, the middleware returns `429 Too Many Requests` with `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers.

### Throttle parameters

```python
Throttle(
    max_attempts=60,         # requests per window
    window_seconds=60,       # window length
    store=...,               # backing store
    key=...,                 # how to derive the rate-limit key
)
```

### Per-user vs per-IP limits

By default `Throttle` keys on the client IP. For authenticated APIs, key on the user ID instead:

```python
Throttle(
    100,
    window_seconds=60,
    key=lambda request: f"user:{request.state.user.id}",
)
```

## Defining named limiters

For richer policies (per-route, per-user, dynamic limits), define a named limiter in a provider:

```python
from arvel.support.rate_limit import RateLimiter, Limit


class RateLimitServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        @RateLimiter.for_("api")
        def api_limit(request):
            user = getattr(request.state, "user", None)
            if user is None:
                return Limit.per_minute(30).by_ip(request)
            if user.is_premium:
                return Limit.per_minute(600).by(user.id)
            return Limit.per_minute(120).by(user.id)
```

Then use the limiter name in your middleware:

```python
with Route.group(middleware=[Throttle.using("api")]):
    @Route.get("/api/me")
    async def me(): ...
```

The limiter callback can return:

- A single `Limit` — applied as the rate limit.
- A list of `Limit`s — all must pass; the strictest applies first.

## Programmatic checks

For ad-hoc throttling outside of middleware (e.g. limiting expensive jobs):

```python
from arvel.facades import RateLimit


key = f"webhook-process:{event.id}"
allowed = await RateLimit.attempt(key, max_attempts=10, window=60)
if not allowed:
    raise ThrottleException("Too many webhook deliveries; backing off.")

await process_webhook(event)
```

## Cleaning up

For in-memory stores, expired keys are evicted lazily. For Redis, keys expire automatically via TTL. For the database driver, run a periodic cleanup task:

```python
from arvel.facades import Schedule


def register_schedule(schedule: Schedule) -> None:
    schedule.command("rate_limit:prune").every_five_minutes()
```

## Where to next?

- [Middleware](middleware.md) — how `Throttle` fits in the pipeline.
- [Cache](cache.md) — same backing stores power both layers.
- [Queues](queues.md) — for shedding load via async processing.
