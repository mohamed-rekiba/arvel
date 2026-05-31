# Clean model syntax — type-inferred columns

## Problem

Model authoring forces a column helper on every field:

```python
class User(Model):
    id: int = id_()
    name: str = string(255)
    age: int | None = integer(nullable=True, default=None)
```

We want the SQLModel-shaped look, where the Python type drives the column and a
helper is only needed for things a type can't express:

```python
class User(Model):
    id: int | None = field(default=None, primary_key=True)
    name: str
    age: int | None = None
```

## Chosen approach

Lean on SQLAlchemy 2.0's native annotated declarative. SQLAlchemy already infers
a column's SQL type from a `Mapped[T]` annotation via `registry.type_annotation_map`
plus a bare `mapped_column()`. The model metaclass already rewrites plain
annotations to `Mapped[...]`. We extend that rewrite to fire for **bare
annotations** and **plain Python defaults**, and add a generic `field(...)` for
the options a type can't carry.

Rejected alternatives:
- Full custom inference (resolve annotation strings → build `Column`s ourselves):
  re-implements what SQLAlchemy does, fragile against internals.
- `field()`-only with no inference: doesn't reach `name: str` / `age: int | None = None`.

## Declaration forms (all coexist)

| Source | Column | `__init__` |
|---|---|---|
| `name: str` | `String(255)`, NOT NULL | required |
| `age: int \| None = None` | `Integer`, nullable, default `None` | optional |
| `count: int = 0` | `Integer`, NOT NULL, default `0` | optional |
| `id: int \| None = field(default=None, primary_key=True)` | `Integer` PK | optional |
| `email: str = string(255, unique=True)` | explicit helper (unchanged) | per-helper |

## Three changes (all in `arvel/database`)

1. **Metaclass inference** — `_ModelMeta.__new__`. For a column-candidate
   annotation (not `ClassVar`/`InitVar`/dunder/already-`Mapped`/method/relationship):
   - bare (no value) → inject `mapped_column()`, wrap annotation `Mapped[T]`.
   - plain default → inject `mapped_column(default=value)`, wrap annotation.
     Mutable column types (`list`/`dict`) have no inferred SQL type, so a bare
     `tags: list = []` errors at mapper config — the intended nudge to `json()`.
   Existing `Mapped[T] = helper()` and `T = helper()` paths untouched.

2. **`registry.type_annotation_map`** on `Model`: `str → String(255)`,
   `datetime → DateTime(timezone=True)`, `Decimal → Numeric(10, 2)`. Everything
   else uses SQLAlchemy defaults. Unmappable bare types surface SQLAlchemy's
   own error (use `json()` / an explicit helper).

3. **`field(...)`** in `columns.py`, returns `Any`, registered in the
   `dataclass_transform` `field_specifiers` tuple. Carries `primary_key`,
   `unique`, `index`, `nullable`, `foreign_key`/`on_delete`/`on_update`,
   `length`, `default`/`default_factory`, `init`, `server_default`. Returns
   `Any` (like SQLModel's `Field`) so `id: int = field(...)` is clean under
   mypy and pyright strict.

## Type safety

- Instance attributes: fully typed (`user.name: str`, `user.age: int | None`).
- Constructor: required vs optional enforced statically and at runtime.
- Zero `# type: ignore`, no widened query API, no `col()` cast — Arvel's query
  API is already `str`/`Any`-typed (`where(*clauses: Any, ...)`), so it never
  relied on `User.name` being a typed column expression.
- Concession: class-level `User.name` is statically the plain type, not an
  `InstrumentedAttribute`. The framework doesn't type-check that. Authors who
  want a typed column expression on a field keep `Mapped[T] = helper()`.

## Helpers

Kept. Inference makes the common 80% need no call; the typed helpers remain the
vocabulary for SQL-specific cases (`text`, `big_integer`, `json`/`jsonb`,
`enum`, `decimal` precision, `foreign_*`, `column` for custom types) and mirror
the migration `Blueprint` DSL. The sugar helpers (`id_`, `string`, `integer`,
`boolean`) stay as optional shorthands.

## Non-goals

- Mass-converting existing models/fixtures (follow-up).
- Class-level typed column expressions for the clean form (Python typing limit).

## Testing

Failing tests first: column type / nullability / default / PK / FK / unique /
index for each form, `__init__` signature, round-trip persistence, datetime &
Decimal inference, enum-member default, plain-default isolation. The test models
double as the mypy/pyright sample (tests are type-checked).
