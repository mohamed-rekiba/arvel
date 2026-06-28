# Factories

Generate model instances for tests and seeders. Subclass `Factory`, set `model`, and implement
`definition()` (use `self.faker` for fake data):

```python
from arvel.database import Factory

class UserFactory(Factory[User]):
    model = User
    def definition(self):
        return {"name": self.faker.name(), "email": self.faker.unique.email()}

await UserFactory().create()                  # one persisted User
user = UserFactory().make(name="Ada")         # one unsaved instance, with an override
UserFactory().raw()                           # just the attribute dict (no model)
```

`count(n)` returns a batch whose `make`/`create` return lists; `state` layers overrides (a dict or
`callable(attrs) -> dict`); `sequence` cycles values across the batch:

```python
await UserFactory().count(3).create()                          # 3 persisted users
await UserFactory().state({"admin": True}).create()            # composable; immutable (returns a copy)
await UserFactory().count(2).sequence({"name": "Alice"}, {"name": "Bob"}).create()
```

Resolution order is `definition()` → `state` (in order) → `sequence[i]` → explicit overrides.

