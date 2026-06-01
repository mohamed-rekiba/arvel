# ADR-022 — `Model` mixes in `MappedAsDataclass` for typed `__init__`

**Status**: Accepted
**Date**: 2026-05-20
**Supersedes**: —
**Related**: ADR-021 (Eloquent-on-SQLA mixin), ADR-024 (Model metaclass forwarding), ADR-065 (Soft-delete global scope), ADR-010 (Two-checker suppression floor)

## Context

`arvel.database.Model` extends `DeclarativeBase` (per ADR-021) and inherits its constructor — `DeclarativeBase.__init__(**kw: Any) -> None`. Construction is therefore **untyped on every keyword**:

```python
User(naem="Alice")            # type-checks; raises at first attribute access
User(name=None)               # type-checks; violates NOT NULL at flush
User("Alice", "a@b.com")      # positional — silently reorders if columns are reordered
```

The 2026-05-20 SQLModel investigation (research 002) confirmed that this is the *only* dimension on which SQLModel beat plain SQLA-2.0 + `Mapped[T]`, and that the underlying capability ships natively in SQLAlchemy via `MappedAsDataclass` — without any of SQLModel's downsides (Pyright **not_planned**, Python 3.14 / PEP 649 incompatibility on forward refs, `Field(...) -> Any`, deprecated Mypy plugin lineage).

The lower-risk lessons (L2-L6) from the same investigation shipped in the 2026-05-20 batch. This ADR governs the deferred L1.

## Decision

`arvel.database.Model` mixes in `MappedAsDataclass(init=True, kw_only=True)` alongside `DeclarativeBase`. The framework mixins (`Timestamps`, `SoftDeletes`) mark server-managed columns as `init=False` so they do not appear in the generated constructor.

```python
class Model(MappedAsDataclass, DeclarativeBase, ActiveRecord,
            metaclass=ModelMeta, init=True, kw_only=True):
    ...
```

## Rationale

1. **First-party SQLA.** `MappedAsDataclass` is shipped by SQLAlchemy itself; no third dependency, no metaclass fusion. Composes cleanly with `ModelMeta` (ADR-024) and `ActiveRecord`.
2. **Typed where the value lives.** The constructor is generated from the same `Mapped[T]` annotations that already drive ORM mapping. One source of truth — the column annotation — for both runtime and types.
3. **Kw-only matches existing idiom.** `User.create(...)` and `User(...)` already read like keyword construction in every example app; positional construction would be a footgun.
4. **No SQLModel.** The alternative of bringing in SQLModel was rejected in research 002 §3.5 — its Pyright behaviour is unsupported (issue marked **not_planned**), it reintroduces Pydantic at the persistence layer (the framework already uses Pydantic strictly at API boundaries via `PydanticType` + `to_pydantic()`), and its `Relationship(...)` forward refs are broken on Python 3.14 / PEP 649, which Arvel targets.

## Consequences

**Positive**:

- Typos in column names (`User(naem=...)`) become type-errors under mypy and pyright strict mode.
- Nullable-vs-non-nullable mistakes (`User(name=None)`) become type-errors when the column is non-nullable.
- The L2 `arvel.database.columns` helpers (`id_`, `string(...)`, …) compose with the typed constructor — they return `Any`, so the plain annotation drives the type (see the column-style update below).
- `make:model` emits the bare helper form (`id: int = id_()`); the model metaclass (`ModelMeta`, ADR-024) wraps it in `Mapped[int]` at runtime. The drift between framework-generated stubs and hand-written models shrinks to zero.

**Negative**:

- Existing internal models / tests / examples that wrote columns without `Mapped[T]` will need annotations. SAD-003 has required this since day one, so the surface should be near zero; verified during rollout.
- `Timestamps` and `SoftDeletes` must pass `init=False` on their managed columns, otherwise every `User(...)` call would demand a `created_at` argument. The mapper-event hook that populates them stays.
- Breaking change for any downstream app that relies on positional construction (none documented).

**Enforcement**:

- The architecture test asserts framework `relationship(...)` declarations use the clean annotation (`test_framework_relationships_use_clean_annotation`), and that the `make:model` stub uses the column helpers (`test_make_model_stub_uses_bare_column_helpers`).
- Type-only tests under `tests/typing/` assert `User(naem=...)` is a pyright/mypy error.

## Update (2026-05-31) — column annotation style

`Mapped[...]` is gone from every model declaration — app code, generated stubs, framework-internal models (`CacheEntry`), the `Timestamps`/`SoftDeletes` mixins, **and relationships**: `id: int = id_()`, `children: list[Post] = relationship(...)`, never the `Mapped[...]` wrapper. Three pieces make this clean under **both** mypy and pyright strict:

- Every column helper in `arvel.database.columns` returns `Any` (like SQLModel's `Field`), and Arvel's `relationship()` is a thin wrapper that also returns `Any`. So the plain annotation is the sole source of the Python type — no SQLAlchemy mypy-plugin dependency, no pyright false positives.
- `ModelMeta` rewrites the annotation to `Mapped[T]` at class-build time and, for a **bare** annotation with no helper (`name: str`), injects a `mapped_column()` to back it. So no-helper columns are clean too. It wraps relationship-bound annotations the same way.
- The framework's own non-`Model` declarative classes get the clean syntax by using `ModelMeta` as their metaclass: the `Timestamps`/`SoftDeletes` mixins (over `MappedAsDataclass`) and the cache store's `_CacheBase` (a standalone `DeclarativeBase`). No special-casing left.

This supersedes the earlier same-day note that had helpers returning `Mapped[T]` and kept `Mapped` for relationships and framework mixins — none of that is needed now.

## Status & Next Step

Implemented in . See `docs/plans/2026-05-20-mapped-as-dataclass-design.md` for the full plan, test strategy, and rollout order.
