# Contracts

In Laravel, "contracts" are interfaces (`Illuminate\Contracts\*`) that define the public surface of framework services. In Arvel, the equivalent role is filled by **typed Protocols** in `arvel.contracts`.

## Why Protocols

- Structural typing — any class that has the right methods satisfies the protocol
- No inheritance required — keeps user code free of framework imports
- `mypy --strict` and `pyright --strict` both verify protocol conformance
- Easy to mock in tests — define your own class that matches the shape

## Example: the Cache contract

```python
from typing import Protocol


class CacheRepository(Protocol):
    async def get(self, key: str, default: Any = None) -> Any: ...
    async def put(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    async def forget(self, key: str) -> None: ...
    async def has(self, key: str) -> bool: ...
```

Every cache driver (array, file, redis, database) satisfies this protocol. Code that takes a `CacheRepository` works with any of them.

## Resolving by protocol

```python
from arvel.contracts.cache import CacheRepository
from arvel.facades import Container

cache = Container.resolve(CacheRepository)
```

Or via dependency injection:

```python
async def handler(cache: Annotated[CacheRepository, arvel.dep(CacheRepository)]) -> None:
    await cache.put("key", "value")
```

## Available contracts

The `arvel.contracts` package exports protocols for every major framework service: `CacheRepository`, `Hasher`, `MailDriver`, `QueueDriver`, `SessionStore`, `Authenticator`, `EventDispatcher`, `Broadcaster`, and more. See the source at [`packages/arvel/src/arvel/contracts/`](https://github.com/mohamed-rekiba/arvel/tree/main/packages/arvel/src/arvel/contracts) for the full list.

## See also

- [Service Container](container.md) — resolving services.
- [Facades](facades.md) — the facade-vs-DI trade-off.
