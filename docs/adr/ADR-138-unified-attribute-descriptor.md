# ADR-138: Unified `Attribute` descriptor

Status: Accepted (delivered WI-arvel-019)

Eloquent-parity increment (backlog `006`, story S5). Adds a single descriptor for symmetric
get/set under one attribute name. No schema or route changes.

## ADR-138-01: A Python data descriptor, not a decorated method

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

## ADR-138-02: `set` returns a column→value mapping

Status: Accepted

A virtual attribute has no column of its own, so a scalar write has nowhere unambiguous to land.
`set` therefore returns a `Mapping[str, Any]` of real column names to values; each is assigned
through the normal `setattr` path (so casts and mutators still run). A non-mapping return raises
`TypeError` at write time. `get`-only attributes are read-only (write raises); `set`-only
attributes are write-only (read raises). For the single-column transform case, the existing
`@mutator` already suffices — `Attribute` targets the multi-column / unified-name case.

## ADR-138-03: Opt-in per-instance caching

Status: Accepted

`.should_cache()` flips a flag. The computed value is memoized in a per-instance dict
(`instance.__dict__["_arvel_attr_cache"]`, set via `object.__setattr__` to skip the cast path)
keyed by attribute name. Writing through the attribute invalidates its own cache entry. Caching
does **not** track column dependencies — mutating a backing column directly leaves a cached value
sticky (same limitation as Laravel's `shouldCache()`); use it only when that's acceptable. The
cache key is excluded from the `model_serialize` `__dict__` fallback.
