# Rate Limiting

arvel includes a simple, cache-backed rate limiter you can combine with any key to restrict the rate
of an action over a window of time — most commonly to throttle inbound HTTP requests, but usable for
anything (an outbound API call, a costly job).

> The rate limiter is backed by the [cache](cache.md). A cache-less app falls back to a process-global
> window (fine for a single running process; use a shared cache-backed store in production).

## Basic usage

Resolve the limiter from the container (or the `RateLimiter` facade) and drive it by a key you choose:

```python
from arvel.support.facades import RateLimiter

async def send_message(user):
    key = f"send-message:{user.id}"
    if await RateLimiter.too_many_attempts(key, max_attempts=5):
        seconds = await RateLimiter.available_in(key)
        abort(429, f"Try again in {seconds}s")
    await RateLimiter.hit(key, decay_seconds=60)     # count this attempt; window = 60s
    # ... send the message
```

Other useful methods:

```python
await RateLimiter.attempts(key)                 # attempts made so far
await RateLimiter.remaining(key, max_attempts)  # attempts left
await RateLimiter.clear(key)                    # reset the counter
```

`attempt()` combines the check-and-hit in one call, running a callback only when there's budget left.

## Named limiters for routes

Define a **named limiter** once — usually in a service provider's `boot` — with a resolver that
returns a `Limit`, then apply it to routes with the `throttle:<name>` middleware string:

```python
from arvel.support.facades import RateLimiter
from arvel.http.rate_limiter import Limit

RateLimiter.for_("api", lambda request: Limit.per_minute(60).by(request.ip()))
```

```python
Route.get("/api/posts", index).middleware("throttle:api")
```

A request over the limit gets a **429** with `Retry-After` and `X-RateLimit-*` headers.

### Building limits

`Limit` is a small fluent builder:

```python
Limit.per_second(10)
Limit.per_minute(60)
Limit.per_hour(1000)
Limit.per_day(10_000)
Limit.per_minute(60).by(request.ip())            # segment the window by a key
Limit.per_minute(5).response(custom_429_handler) # custom over-limit response
```

`.by(key)` gives each caller (per IP, per user, per tenant) an independent window; without it, the
limit is shared across everyone hitting that route.

## See also

- [Middleware](middleware.md) — how `throttle:<name>` is resolved and applied.
- [Cache](cache.md) — the store the limiter counts in.
- [Requests](requests.md) — `request.ip()` and other segmenting keys.
