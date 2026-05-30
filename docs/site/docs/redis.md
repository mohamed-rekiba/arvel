# Redis

Redis is a first-class supporting service in Arvel. Many subsystems (cache, sessions, queues, broadcasting, rate limiter) can be backed by Redis.

## Configuration

```env
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_POOL_SIZE=10
```

```python
# config/redis.py
class RedisSettings(ArvelSettings):
    url: SecretStr
    pool_size: int = 10
```

## Using Redis directly

```python
from arvel.facades import Redis

await Redis.set("user:42:profile", "...", ex=3600)
value = await Redis.get("user:42:profile")
await Redis.delete("user:42:profile")
```

The facade wraps `redis-py` (`redis.asyncio`), so the full async API is available.

## Pub/Sub

```python
async with Redis.pubsub() as pubsub:
    await pubsub.subscribe("notifications")
    async for message in pubsub.listen():
        if message["type"] == "message":
            print(message["data"])
```

## Subsystems using Redis

| Subsystem | Set via env | See |
|---|---|---|
| Cache | `CACHE_DRIVER=redis` | [Cache](cache.md) |
| Sessions | `SESSION_DRIVER=redis` | [Session](session.md) |
| Queues | `QUEUE_DRIVER=redis` | [Queues](queues.md) |
| Rate Limiting | `RATE_LIMITER_STORE=redis` | [Rate Limiting](rate-limiting.md) |

## Connection pooling

The facade maintains a single shared connection pool (sized by `REDIS_POOL_SIZE`). For long-running jobs that hold a connection (`SUBSCRIBE`, `BLPOP`), use `Redis.connection()` to acquire a dedicated connection.

## See also

- [Cache](cache.md) — Redis as a cache driver.
- [Queues](queues.md) — Redis as a queue driver.
- [Broadcasting](broadcasting.md) — Redis as a Reverb backplane.
