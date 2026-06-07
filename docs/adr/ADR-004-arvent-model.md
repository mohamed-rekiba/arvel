# ADR-004 — Arvent — Model & ActiveRecord layer

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-06-01; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Mixin-on-SQLAlchemy approach, MappedAsDataclass on Model, clean type-inferred column syntax, metaclass query forwarding, ModelCollection return type.

## Why this is one ADR

These five decisions design Arvent's Model class — how it sits on top of SQLAlchemy, what the user-facing column syntax looks like, and what queries return. They are inseparable: each justifies the next.

---

## § 1 — Arvent is a mixin on SQLAlchemy, not a fork

**Originally**: ADR-021 · Date: 2026-05-17

### Context

Laravel's Eloquent is the gold standard for ActiveRecord ergonomics. Python
already has SQLAlchemy with first-class async support, fully typed
`Mapped[...]` annotations, and a mature query construction API. Three options
were considered:

| Option | Pros | Cons |
|---|---|---|
| A. Custom ORM (Masonite-style) | Total control over DX | Years of work to match SQLA's edge cases (identity map, unit of work, autoflush, polymorphic loading, etc.) |
| B. Light wrapper around SQLA Core (Uvicore-style) | Type-safe; less magic | Loses ActiveRecord ergonomics; falls back to data-mapper everywhere |
| C. **Mixin on SQLA 2.0 `DeclarativeBase`** | Eloquent-grade DX for free + SQLA's maturity; no schema fork | Some Laravel idioms (lazy-load-by-default) don't translate — we steer users toward eager-loading instead |

### Decision

Option C. `arvel.database.Model` extends SQLA 2.0 `DeclarativeBase` and applies
the `ActiveRecord` mixin pre-mounted. Every column type, relationship, and
query primitive is backed by an existing SQLA primitive. No re-implementation
of features SQLA already provides.

### Consequences

**Positive**:
- Users with SQLA experience are immediately productive.
- We inherit SQLA's bug fixes and performance improvements automatically.
- `mypy --strict` and `pyright --strict` "just work" because SQLA 2.0's
  `Mapped[...]` annotations are already first-class.
- Migrations through Alembic come for free.

**Negative**:
- Lazy-load by default doesn't translate well — async + lazy = footgun. We
  default to `lazy="raise"` on relations in the example apps and DX docs.
- Some Eloquent idioms (`whereHas`, `whereDoesntHave`) become SQLA `any()` /
  `has()` queries; we provide thin sugar but encourage SQLA expressions.

**Enforcement**:
- Code review checklist line item: "Does this re-implement a SQLA feature?"
  → reject and use the SQLA primitive.

---

### Merged: Remove Sync Shadow Methods from BaseModelMixin (was ADR-004 § 1)

**Date**: 2026-05-24
**Status**: Accepted

### Context

`BaseModelMixin` in `arvel-ecommerce-demo` defines sync `delete()`, `restore()`,
`scope_active()`, `to_dict()`, and `__post_init__`. Because `BaseModelMixin` appears first
in every model's MRO, it shadows the async equivalents from `ActiveRecord` / `SoftDeletes`.

Consequence: routes can never `await product.delete()` — the sync method executes and
returns `None`, and `await None` raises `TypeError`. All route handlers bypass the framework
by using `DB.statement("UPDATE ... SET deleted_at = ...")` instead.

### Decision

Remove `delete()`, `restore()`, `scope_active()`, `to_dict()`, and `__post_init__` from
`BaseModelMixin`. After removal, MRO resolution reaches `ActiveRecord.delete()` (async),
which already handles soft-delete via `__arvel_soft_delete_column__`.

The unit test `test_model_mixins.py::TestBaseModelMixin` that calls `p.delete()` sync is
updated: the tests set `p.deleted_at` directly or are removed, as the async counterparts
are covered by integration tests.

### Consequences

- Routes can now call `await product.delete()` / `await product.restore()` correctly
- No raw SQL `UPDATE ... SET deleted_at = :now` needed in services or routes
- Unit tests that tested sync behavior are updated to set attribute directly
- `BaseModelMixin` now contains only: class docstring and the `uuid7` re-export line

---

## § 2 — `Model` mixes in `MappedAsDataclass` for typed `__init__`

**Originally**: ADR-022 · Date: 2026-05-20

### Context

`arvel.database.Model` extends `DeclarativeBase` (per ADR-004 § 1) and inherits its constructor — `DeclarativeBase.__init__(**kw: Any) -> None`. Construction is therefore **untyped on every keyword**:

```python
User(naem="Alice")            # type-checks; raises at first attribute access
User(name=None)               # type-checks; violates NOT NULL at flush
User("Alice", "a@b.com")      # positional — silently reorders if columns are reordered
```

The 2026-05-20 SQLModel investigation (research 002) confirmed that this is the *only* dimension on which SQLModel beat plain SQLA-2.0 + `Mapped[T]`, and that the underlying capability ships natively in SQLAlchemy via `MappedAsDataclass` — without any of SQLModel's downsides (Pyright **not_planned**, Python 3.14 / PEP 649 incompatibility on forward refs, `Field(...) -> Any`, deprecated Mypy plugin lineage).

The lower-risk lessons (L2-L6) from the same investigation shipped in the 2026-05-20 batch. This ADR governs the deferred L1.

### Decision

`arvel.database.Model` mixes in `MappedAsDataclass(init=True, kw_only=True)` alongside `DeclarativeBase`. The framework mixins (`Timestamps`, `SoftDeletes`) mark server-managed columns as `init=False` so they do not appear in the generated constructor.

```python
class Model(MappedAsDataclass, DeclarativeBase, ActiveRecord,
            metaclass=ModelMeta, init=True, kw_only=True):
    ...
```

### Rationale

1. **First-party SQLA.** `MappedAsDataclass` is shipped by SQLAlchemy itself; no third dependency, no metaclass fusion. Composes cleanly with `ModelMeta` (ADR-004 § 4) and `ActiveRecord`.
2. **Typed where the value lives.** The constructor is generated from the same `Mapped[T]` annotations that already drive ORM mapping. One source of truth — the column annotation — for both runtime and types.
3. **Kw-only matches existing idiom.** `User.create(...)` and `User(...)` already read like keyword construction in every example app; positional construction would be a footgun.
4. **No SQLModel.** The alternative of bringing in SQLModel was rejected in research 002 §3.5 — its Pyright behaviour is unsupported (issue marked **not_planned**), it reintroduces Pydantic at the persistence layer (the framework already uses Pydantic strictly at API boundaries via `PydanticType` + `to_pydantic()`), and its `Relationship(...)` forward refs are broken on Python 3.14 / PEP 649, which Arvel targets.

### Consequences

**Positive**:

- Typos in column names (`User(naem=...)`) become type-errors under mypy and pyright strict mode.
- Nullable-vs-non-nullable mistakes (`User(name=None)`) become type-errors when the column is non-nullable.
- The L2 `arvel.database.columns` helpers (`id_`, `string(...)`, …) compose with the typed constructor — they return `Any`, so the plain annotation drives the type (see the column-style update below).
- `make:model` emits the bare helper form (`id: int = id_()`); the model metaclass (`ModelMeta`, ADR-004 § 4) wraps it in `Mapped[int]` at runtime. The drift between framework-generated stubs and hand-written models shrinks to zero.

**Negative**:

- Existing internal models / tests / examples that wrote columns without `Mapped[T]` will need annotations. SAD-003 has required this since day one, so the surface should be near zero; verified during rollout.
- `Timestamps` and `SoftDeletes` must pass `init=False` on their managed columns, otherwise every `User(...)` call would demand a `created_at` argument. The mapper-event hook that populates them stays.
- Breaking change for any downstream app that relies on positional construction (none documented).

**Enforcement**:

- The architecture test asserts framework `relationship(...)` declarations use the clean annotation (`test_framework_relationships_use_clean_annotation`), and that the `make:model` stub uses the column helpers (`test_make_model_stub_uses_bare_column_helpers`).
- Type-only tests under `tests/typing/` assert `User(naem=...)` is a pyright/mypy error.

### Update (2026-05-31) — column annotation style

`Mapped[...]` is gone from every model declaration — app code, generated stubs, framework-internal models (`CacheEntry`), the `Timestamps`/`SoftDeletes` mixins, **and relationships**: `id: int = id_()`, `children: list[Post] = relationship(...)`, never the `Mapped[...]` wrapper. Three pieces make this clean under **both** mypy and pyright strict:

- Every column helper in `arvel.database.columns` returns `Any` (like SQLModel's `Field`), and Arvel's `relationship()` is a thin wrapper that also returns `Any`. So the plain annotation is the sole source of the Python type — no SQLAlchemy mypy-plugin dependency, no pyright false positives.
- `ModelMeta` rewrites the annotation to `Mapped[T]` at class-build time and, for a **bare** annotation with no helper (`name: str`), injects a `mapped_column()` to back it. So no-helper columns are clean too. It wraps relationship-bound annotations the same way.
- The framework's own non-`Model` declarative classes get the clean syntax by using `ModelMeta` as their metaclass: the `Timestamps`/`SoftDeletes` mixins (over `MappedAsDataclass`) and the cache store's `_CacheBase` (a standalone `DeclarativeBase`). No special-casing left.

This supersedes the earlier same-day note that had helpers returning `Mapped[T]` and kept `Mapped` for relationships and framework mixins — none of that is needed now.

---

## § 3 — Clean model syntax: type-inferred columns + `field()`

**Originally**: ADR-023 · Date: 2026-06-01 · Status: Accepted (delivered)

### Context

ADR-004 § 2 made `Model` construction typed and removed the `Mapped[...]` wrapper from declarations, but a column still needed an explicit helper on every field:

```python
class User(Model):
    id: int = id_()
    name: str = string(255)
    age: int | None = integer(nullable=True, default=None)

## OR

class User(Model):
    id: int | None = field(default=None, primary_key=True)
    name: str
    age: int | None = None
```

SQLAlchemy 2.0 already infers a column's SQL type from a `Mapped[T]` annotation via `registry.type_annotation_map` plus a bare `mapped_column()`. `ModelMeta` (ADR-004 § 4) already rewrites plain annotations to `Mapped[...]`. The question was whether to lean on that or build custom inference.

### Decision

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

### Rationale

1. **First-party inference.** `type_annotation_map` + bare `mapped_column()` is SQLAlchemy's own mechanism. No annotation-string parsing, no custom `Column` builder to keep in sync with SQLA releases.
2. **One source of truth.** The plain annotation drives both the runtime column and the static type. Helpers and `field()` return `Any`, so there's no SQLAlchemy mypy-plugin dependency and no pyright false positives — clean under `mypy --strict` and `pyright --strict` with zero suppressions.
3. **Helpers stay the vocabulary for SQL-specific types.** Inference covers the common 80%; `text`, `jsonb`, `enum`, `decimal` precision, `foreign_*`, `uuid_id`, and `column` (custom `TypeDecorator`) remain explicit and mirror the migration `Blueprint` DSL.

### Consequences

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

---

## § 4 — Model Class-Level QB Forwarding via Metaclass

**Originally**: ADR-024 · Date: 2026-05-18

### Decision

Add `_ModelMeta(DeclarativeAttributeIntercept)` to `Model`. Its `__getattr__` forwards unknown class-level attribute accesses to `cls.query()`.

### Context

Laravel's Eloquent allows `User::where(...)` directly on the model class via PHP's `__callStatic`. Without an equivalent, arvel requires `User.where(...)` — a visible ergonomic gap.

### Options

**A. Explicit method list** — add `where`, `find`, `order_by`, etc. as `@classmethod` wrappers. Maintenance burden: every new QB method needs a parallel classmethod.

**B. `__init_subclass__` loop** — iterate over QB methods and inject classmethods at subclass definition time. Fragile: captures QB methods at class definition, not at call time; doesn't handle methods added later.

**C. Metaclass `__getattr__`** ← chosen. Fires only for missing names; zero maintenance; type-safe with proper stubs.

### Consequences

- `User.where(...)`, `User.order_by(...)`, `User.with_("posts")` all work without `.query()`
- `User.find(1)`, `User.create({...})`, `User.query()` remain explicit classmethods (take precedence over `__getattr__`)
- `pyright --strict` requires a stub or `# type: ignore` comment at the `metaclass=_ModelMeta` line due to SQLAlchemy's internal typing — acceptable, isolated to one line

---

## § 5 — ModelCollection for Arvent model result sets

**Originally**: ADR-028

Status: Accepted (delivered WI-arvel-037)

Epic 006 Story 8. `QueryBuilder.all()`/`get()` now return a `ModelCollection` — a
`Collection` subclass with the PK- and relation-aware helpers Arvent needs for
model rows (the same helpers Laravel ships on `Eloquent\Collection`).

### Context

`all()` returned the generic `Collection` (a `list` subclass with map/filter/pluck). That's
fine for scalar rows, but model result sets want key-based lookups, batch relation loading, and
re-fetching — the operations Eloquent's model collection provides. Raw/dict result rows
(`select_raw`, `select(cols)`) stay on the plain `Collection`.

### ADR-004 § 5-01: subclass, not a new type

Status: Accepted

`ModelCollection(Collection[T])` inherits every existing helper, so nothing that already treats a
result as a list or a `Collection` breaks. Only the model-row return paths in `all()` switch to
`ModelCollection`; dict and raw-SQL rows keep returning `Collection`.

### ADR-004 § 5-02: key-aware operations

Status: Accepted

`model_keys()`, `find(key)`, `contains(key|model|predicate)`, `only(*keys)`, `except_(*keys)`,
`diff(other)`, and `intersect(other)` all key off `get_key()` (the model's PK) rather than object
identity — overriding the base `Collection.find`/`only`/`except_`/`contains`/`diff`/`intersect`,
which compare by value or object identity.

### ADR-004 § 5-03: batch load / load_missing

Status: Accepted

`load(*relations)` splits requests into async descriptor relations (BelongsToMany / MorphToMany /
MorphOne / MorphMany — routed through the epic-007 `load_async_relation_path`, batched across all
members) and plain SQLAlchemy relations (one `select(model).where(pk IN keys)` with `selectinload`,
results copied onto each member by key). Either way it's a fixed number of queries, never N+1.
`load_missing` only loads relations not yet populated on at least one member.

### ADR-004 § 5-04: to_query / fresh

Status: Accepted

`to_query()` returns a `QueryBuilder` scoped to `WHERE pk IN (model_keys)`. `fresh(*relations)`
captures the ordered keys, expires the members (so bulk-update writes that bypassed the identity
map are re-read), re-queries by key with the requested relations eager-loaded, and returns a new
`ModelCollection` in the original order (rows deleted in the meantime drop out).

### ADR-004 § 5-05: serialization visibility

Status: Accepted

`make_hidden(*fields)` / `make_visible(*fields)` fan the per-instance visibility helpers out across
every member and return `self` for chaining.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-021 | 2026-05-17 | Arvent is a mixin on SQLAlchemy, not a fork | § 1 |
| ADR-022 | 2026-05-20 | `Model` mixes in `MappedAsDataclass` for typed `__init__` | § 2 |
| ADR-023 | 2026-06-01 | Clean model syntax: type-inferred columns + `field()` | § 3 |
| ADR-024 | 2026-05-18 | Model Class-Level QB Forwarding via Metaclass | § 4 |
| ADR-028 | — | ModelCollection for Arvent model result sets | § 5 |
