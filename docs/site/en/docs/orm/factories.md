# Factories

Tests need data — lots of it, cheaply, and with just enough realism to exercise constraints. **ModelFactory** generates `ArvelModel` instances for unit tests (`make`) and persists them through an async session (`create`, `create_many`).

Factories are plain subclasses: you declare `__model__`, override `defaults()`, and optionally define named **states** for common variations.

## A minimal factory

```python
from typing import Any, ClassVar

from arvel.testing.factory import ModelFactory


class UserFactory(ModelFactory[User]):
    __model__: ClassVar[type[User]] = User

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        seq = cls._next_seq()
        return {
            "name": f"User {seq}",
            "email": f"user{seq}@test.example",
        }
```

`_next_seq()` gives a per-class counter so emails stay unique across examples.

## Making instances

```python
user = UserFactory.make()
user = await UserFactory.create(session=session)
users = await UserFactory.create_many(5, session=session)
```

`make` never touches the database — perfect for fast pure tests. `create` flushes and refreshes so autoincrement IDs and server defaults are visible.

## States

Define `state_<name>()` class methods returning override dicts, then chain `UserFactory.state("admin")`:

```python
@classmethod
def state_admin(cls) -> dict[str, Any]:
    return {"role": "admin", "name": "Admin User"}
```

```python
admin = await UserFactory.state("admin").create(session=session)
```

`FactoryBuilder` is the object returned by `state()` — it supports `make`, `create`, `create_many`, and `make_batch` with the state merged in.

## Batches

`make_batch` and `batch` / `create_many` generate multiple rows with the same overrides. Override per-call kwargs when only a few fields differ.

## Resetting sequences

Call `_reset_seq()` in test teardown if a class-level counter would otherwise leak across examples — rare, but available for strict isolation.

Factories trade a little upfront code for immense downstream speed: readable tests, fewer fixtures, and confidence that your schema rules actually hold.
