# ADR-051: Unified `Attribute` descriptor

Status: Accepted (delivered WI-arvel-019)

Eloquent-parity increment (backlog `006`, story S5). Adds a single descriptor for symmetric
get/set under one attribute name. No schema or route changes.

## ADR-051-01: A Python data descriptor, not a decorated method

Status: Accepted

Laravel declares `protected function name(): Attribute` returning `Attribute::make(get:, set:)`.
The idiomatic Python equivalent is a **data descriptor** assigned to a class attribute:

```python
full_name = Attribute.make(
    get=lambda m: f"{m.first_name} {m.last_name}",
    set=lambda m, v: dict(zip(("first_name", "last_name"), v.split(" ", 1))),
)
```

`Attribute` defines `__get__`/`__set__`/`__set_name__`. Because `Model.__getattribute__` and
`__setattr__` both delegate to `super()` (i.e. `object`), the descriptor protocol fires
normally — reads call `get(model)`, writes call `set(model, value)`. No metaclass collection is
needed (unlike `@accessor`/`@mutator`, which are scanned in `__init_subclass__`).

It carries no annotation, so SQLAlchemy's `MappedAsDataclass` ignores it (not a field, not a
mapped column) — same as the `property` produced by `@accessor`.

## ADR-051-02: `set` returns a column→value mapping

Status: Accepted

A virtual attribute has no column of its own, so a scalar write has nowhere unambiguous to land.
`set` therefore returns a `Mapping[str, Any]` of real column names to values; each is assigned
through the normal `setattr` path (so casts and mutators still run). A non-mapping return raises
`TypeError` at write time. `get`-only attributes are read-only (write raises); `set`-only
attributes are write-only (read raises). For the single-column transform case, the existing
`@mutator` already suffices — `Attribute` targets the multi-column / unified-name case.

## ADR-051-03: Opt-in per-instance caching

Status: Accepted

`.should_cache()` flips a flag. The computed value is memoized in a per-instance dict
(`instance.__dict__["_arvel_attr_cache"]`, set via `object.__setattr__` to skip the cast path)
keyed by attribute name. Writing through the attribute invalidates its own cache entry. Caching
does **not** track column dependencies — mutating a backing column directly leaves a cached value
sticky (same limitation as Laravel's `shouldCache()`); use it only when that's acceptable. The
cache key is excluded from the `model_serialize` `__dict__` fallback.

---

## Merged: Attribute API polish bundle (was ADR-051)

Status: Accepted (delivered WI-arvel-025)

Eloquent-parity increment (backlog `006`, story S14) — the last of Epic 006. Fills in the remaining
model helper surface. No schema change.

## ADR-051-01: Per-instance appends

Status: Accepted

`append(*names)` adds accessor names to one instance's serialized output; `set_appends(list)`
replaces the per-instance list. Stored in a `_instance_appends` ClassVar slot (set via
`object.__setattr__`, like `_instance_hidden`) so it stays out of dataclass/ORM field processing.
`to_dict()` merges class-level `__appends__` with the per-instance list via `_collect_appends()`
(extracted to keep `to_dict` under the complexity gate).

## ADR-051-02: Conditional visibility

Status: Accepted

`make_hidden_if(condition, *fields)` / `make_visible_if(...)` apply the existing
`make_hidden`/`make_visible` only when `condition` holds. `condition` is a bool or a
`self`-predicate (`Callable[[model], bool]`), matching Laravel's bool-or-Closure form. Both return
`self` for chaining.

## ADR-051-03: `only` / `except_`

Status: Accepted

Subset helpers over `to_dict()`: `only(*keys)` keeps just those keys (missing ones skipped);
`except_(*keys)` drops them. `except_` is spelled with a trailing underscore — `except` is a Python
keyword.

## ADR-051-04: Key + column helpers

Status: Accepted

`get_key_name()` (classmethod) returns the single PK column name and raises on composite keys;
`get_key()` returns the PK value (a tuple for composite keys). `qualify_column(col)` prefixes the
table name (`"users.email"`), resolved from the mapper's local table. `is_same(other)` is true for
the same model type with the same non-null key; `is_not` is its inverse — Laravel's `is()`/`isNot()`.

## ADR-051-05: `discard_changes`

Status: Accepted

Reverts pending (dirty) column attributes back to their committed originals via SQLAlchemy's
`committed_state`, leaving the instance clean. Unflushed values with no committed original are left
as-is (nothing to revert to).

## ADR-051-06: `HasUuids` / `HasUlids` traits

Status: Accepted

Plain mixins (not `MappedAsDataclass` — they add no columns) that auto-fill an empty single-column
string PK on insert via a shared `before_insert` hook. The hook calls `type(target).new_unique_id()`
so each trait supplies its own generator: `HasUuids` → `uuid4`; `HasUlids` → a 26-char Crockford
base32 ULID (48-bit ms time + 80-bit `os.urandom`, sortable by the 10-char time prefix; randomness
within a single millisecond isn't monotonic, which is fine for keys). The model declares the PK as a
string column with `init=False, default=None` so it stays empty until the hook runs. `new_unique_id`
is a classmethod, overridable. A `_UniqueIdProvider` Protocol keeps the hook type-safe without
`Any`-widening.
