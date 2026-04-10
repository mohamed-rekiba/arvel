# Mutators and Casts

HTTP payloads arrive as strings; databases store decimals, JSON, and datetimes. **Casts** bridge the gap declaratively on `ArvelModel`, while **accessors** let you expose computed attributes that are not backed by a column.

Together they keep serializers thin and repositories honest: the model knows how values should look coming in and going out.

## Declaring casts

`__casts__` maps attribute names to caster specifications — built-in names like `"int"` or `"json"`, concrete caster classes, or callables resolved through Arvel’s caster registry.

```python
class User(ArvelModel):
    __tablename__ = "users"

    __casts__ = {
        "settings": "json",
        "is_admin": "bool",
    }
```

When attributes are read or written, Arvel runs them through the resolved `Caster`, so validation layers see Python-native objects instead of raw driver output.

## Why casts matter for async ORM

Without casts, every caller would remember to parse JSON or coerce bools. Centralizing that behavior means fewer branches in controllers and a single place to adjust when the schema evolves.

## Accessors

Accessors are discovered from naming conventions on your model — methods that follow the `getFooAttribute` style (see the implementation’s accessor registry for the exact patterns Arvel recognizes). They participate in serialization when you append attribute names to `__appends__`, similar to Laravel’s hidden/visible and append lists.

Use accessors for **derived** values: full name from first and last, formatted currency, or a signed URL that should never be stored.

## Mutators (setters)

Pair mutators with casts when you need asymmetric behavior — for example, normalizing email addresses on write while still exposing them as simple strings on read.

## Custom caster classes

For domain-specific types (money value objects, ULIDs, enums), implement a `Caster` subclass that knows how to convert to and from the database representation. Register it once, reference it in `__casts__`, and every model shares the logic.

## Guardrails

Casts apply at the model boundary, not inside arbitrary SQL expressions — when you filter in the query builder, you still compare against real column types (`User.is_active == True`, not `"1"`).

Mutators and casts are the polish that makes a data layer feel intentional: incoming data becomes trustworthy Python objects, and outgoing data stays consistent for every caller.
