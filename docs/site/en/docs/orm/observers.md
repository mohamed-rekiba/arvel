# Observers

Sometimes a model save should ripple outward — write an audit row, sync a search index, or invalidate a cache. **Observers** let you react to lifecycle moments without stuffing side effects into every repository call.

`ModelObserver` defines async hooks; `ObserverRegistry` wires observers to models (by class or by name) and dispatches them in priority order during transactions.

## Hook overview

Hooks cover the full lifecycle: `saving`, `saved`, `creating`, `created`, `updating`, `updated`, `deleting`, `deleted`, plus soft-delete specific `force_deleting`, `force_deleted`, `restoring`, and `restored`.

Methods that run **before** the operation (`creating`, `updating`, `deleting`, …) may return `False` to abort — the repository turns that into a typed exception so callers can handle it deliberately.

## Typed observers

Subclass `ModelObserver[YourModel]` so each hook receives a precisely typed instance:

```python
from arvel.data.observer import ModelObserver


class UserObserver(ModelObserver[User]):
    async def creating(self, instance: User) -> bool:
        instance.email = instance.email.lower()
        return True

    async def created(self, instance: User) -> None:
        await send_welcome_email(instance)
```

Keep hooks **fast** — heavy work belongs in queued jobs, triggered from `created` or similar.

## Registering observers

```python
registry = ObserverRegistry()
registry.register(User, UserObserver(), priority=10)
```

Lower priority numbers run earlier. Registering by string name (`"User"`) helps when modules cannot import each other directly.

Repositories and transactions receive the registry; if none is provided, a no-op registry is used so tests stay simple.

## Working with transactions

Observers run in the same transaction as the originating `create` / `update` / `delete`. If your hook raises, the transaction rolls back. If a pre-hook returns `False`, Arvel aborts before hitting the database.

That transactional coupling is powerful: you get atomicity between your domain row and the side effects that must stay in sync.

## When not to use observers

Business rules that change the meaning of an operation usually belong in a **service layer** where they are easier to test in isolation. Observers shine for cross-cutting, model-scoped reactions — not for every piece of domain logic.

Used well, observers keep models thin and repositories predictable: save the user, and the rest of the system notices through a clean, ordered pipeline.
