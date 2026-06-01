# ADR-023 — Clean model syntax: type-inferred columns + `field()`

**Status**: Accepted (delivered)
**Date**: 2026-06-01
**Supersedes**: —
**Related**: ADR-024 (Model metaclass forwarding), ADR-022 (`MappedAsDataclass` for typed `__init__`), ADR-134 (`Model.id` VARCHAR)

## Context

ADR-022 made `Model` construction typed and removed the `Mapped[...]` wrapper from declarations, but a column still needed an explicit helper on every field:

```python
class User(Model):
    id: int = id_()
    name: str = string(255)
    age: int | None = integer(nullable=True, default=None)
```

The 2026-05-31 design pass (`docs/plans/2026-05-31-clean-model-syntax-design.md`) targeted the SQLModel-shaped look, where the Python type drives the column and a helper is only needed for what a type can't express:

```python
class User(Model):
    id: int | None = field(default=None, primary_key=True)
    name: str
    age: int | None = None
```

SQLAlchemy 2.0 already infers a column's SQL type from a `Mapped[T]` annotation via `registry.type_annotation_map` plus a bare `mapped_column()`. `ModelMeta` (ADR-024) already rewrites plain annotations to `Mapped[...]`. The question was whether to lean on that or build custom inference.

## Decision

Extend `ModelMeta` to infer a column from a **bare annotation** or a **plain Python default**, register a Laravel-flavored `type_annotation_map` on `Model`, and add a generic `field()` for the options a type can't carry. Four declaration forms now coexist:

| You write | You get | In `__init__` |
|---|---|---|
| `title: str` | `VARCHAR(255)`, NOT NULL | required |
| `views: int = 0` | `INTEGER`, NOT NULL, default `0` | optional |
| `published_at: datetime \| None = None` | nullable, tz-aware `TIMESTAMP` | optional |
| `id: int \| None = field(default=None, primary_key=True)` | `INTEGER PRIMARY KEY` | optional |
| `email: str = string(255, unique=True)` | explicit helper (unchanged) | per-helper |

Three changes, all in `arvel/database` (implemented in commit `ea0eccc`):

1. **Metaclass inference** — `ModelMeta.__new__`. For a column-candidate annotation (not dunder / `ClassVar` / `InitVar` / already-`Mapped` / helper-assigned / relationship): a bare annotation injects `mapped_column()`; a plain default injects `mapped_column(default=value)`. The annotation is then wrapped to `Mapped[T]` so SQLAlchemy resolves the SQL type.

2. **`type_annotation_map`** (ClassVar on `Model`): `str → String(255)`, `datetime → DateTime(timezone=True)`, `Decimal → Numeric(10, 2)`. Every other scalar uses SQLAlchemy's default mapping.

3. **`field(...)`** in `columns.py`, registered in the `dataclass_transform` `field_specifiers`. Carries `primary_key`, `unique`, `index`, `nullable`, `foreign_key` / `on_delete` / `on_update`, `length`, `default` / `default_factory`, `init`, `server_default`. Returns `Any` — like SQLModel's `Field` — so the annotation is the single source of the Python type.

**Rejected alternatives** (from the design doc):

- *Full custom inference* (resolve annotation strings → build `Column`s ourselves): re-implements SQLAlchemy, fragile against its internals.
- *`field()`-only, no inference*: doesn't reach the bare `name: str` / `age: int | None = None` forms that motivated the change.

## Rationale

1. **First-party inference.** `type_annotation_map` + bare `mapped_column()` is SQLAlchemy's own mechanism. No annotation-string parsing, no custom `Column` builder to keep in sync with SQLA releases.
2. **One source of truth.** The plain annotation drives both the runtime column and the static type. Helpers and `field()` return `Any`, so there's no SQLAlchemy mypy-plugin dependency and no pyright false positives — clean under `mypy --strict` and `pyright --strict` with zero suppressions.
3. **Helpers stay the vocabulary for SQL-specific types.** Inference covers the common 80%; `text`, `jsonb`, `enum`, `decimal` precision, `foreign_*`, `uuid_id`, and `column` (custom `TypeDecorator`) remain explicit and mirror the migration `Blueprint` DSL.

## Consequences

**Positive**:

- The common case needs no helper: `name: str`, `views: int = 0`, `published_at: datetime | None = None`.
- `field(...)` gives a SQLModel-shaped escape hatch for cross-cutting options (PK, unique, index, FK, length) without dropping to `mapped_column(...)`.
- Mutable defaults can't leak across instances: `_PLAIN_DEFAULT_TYPES` is a **closed allowlist** of immutable, literal-ish types, so a bare `tags: list = []` is never folded into a shared column default — it errors at mapper config instead, the intended nudge to `json()`.

**Negative** (constraints model authors must know):

- **Every annotated, non-`ClassVar` attribute on a `Model` becomes a column.** Model *config* — a default guard name, a feature flag, a cache key — must be a `ClassVar`, or inference maps it to a column you never wanted (this surfaced as a Postgres `column ... does not exist` mismatch during rollout).
- **Bare non-scalar annotations don't infer.** A bare `list` / `dict` has no SQL type and errors at mapper config — use `json()`. A relationship still needs `relationship(...)`; a bare `posts: list[Post]` with no value is treated as a (failing) column, not a relation.
- **`field(foreign_key=...)` does not auto-index.** Unlike `foreign_id()` (which defaults `index=True`), a `field()` foreign key is unindexed unless you pass `index=True`. Same FK, different default.
- **PK ergonomics differ between `field()` and `id_()`.** `field(primary_key=True)` defaults `init=True` and relies on SQLAlchemy's implicit integer autoincrement; `id_()` defaults `init=False` and sets `autoincrement` explicitly. Prefer `id_()` / `uuid_id()` for server-filled primary keys.
- **Class-level attribute access is the plain type, not an `InstrumentedAttribute`.** `User.name` is statically `str`, not a typed column expression. Arvel's query API is already `str`/`Any`-typed, so this doesn't affect querying; authors who want a typed column expression on a field keep the `Mapped[T] = helper()` form.

**Enforcement**:

- `packages/arvel/tests/database/test_clean_model_syntax.py` exercises each form (column type, nullability, default, PK, FK, unique, index, `__init__` signature, round-trip persistence) and doubles as the mypy/pyright strict sample.
- The architecture guard `test_arvel_model_module_has_no_untyped_mapped_columns` keeps inference routed through `_inferred_column(...)` rather than a literal `mapped_column(` in the model body.

## Status & Next Step

Implemented in commit `ea0eccc`. All framework, package, and demo models plus test fixtures are converted to the clean form. See `docs/plans/2026-05-31-clean-model-syntax-design.md` for the full plan and test strategy.
