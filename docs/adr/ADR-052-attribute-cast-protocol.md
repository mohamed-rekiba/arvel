# ADR-052: Attribute-level Custom Cast Protocol

Status: Accepted

Eloquent-parity increment (backlog `006`, Sprint B: story S1). No HTTP or schema
surface — recorded as an ADR.

## ADR-052-01: `CastsAttributes` ABC with get / set / serialize

Status: Accepted

`__casts__` previously took only built-in type names (`"boolean"`, `"int"`, …). To
support virtual/computed/multi-column casts without changing the SQLAlchemy column
type, `__casts__` values now also accept a `CastsAttributes` subclass or instance:

```python
class AsUpper(CastsAttributes[str]):
    def get(self, model, key, value): return value.upper()
    def set(self, model, key, value): return value.lower()

class Doc(Model):
    __casts__ = {"code": AsUpper}   # class or AsUpper() instance
```

`get`/`set` are abstract; `serialize` defaults to returning the get value, so simple
casts don't have to implement it. `to_dict` calls `serialize` for custom-cast fields,
matching Laravel's `CastsAttributes` + `SerializesCastableAttributes`.

## ADR-052-02: Resolve casts once at class definition, not per access

Status: Accepted

`__getattribute__` runs on **every** attribute read, so parsing cast specs or
instantiating cast classes there would tax the hot path. Instead `__init_subclass__`
resolves each `__casts__` entry once into a `_ResolvedCast(read, write, serialize)`
triple cached on `cls.__arvel_cast_resolvers__`. The read/write paths then do a single
dict lookup and at most one call. Each callable has the uniform
`(model, key, value) -> value` shape; built-in coercers are adapted to ignore
`model`/`key`. This also lets validation happen at definition time (bad spec → raise on
class creation, as before).

## ADR-052-03: Parameterized string specs; `decimal:N` first

Status: Accepted

String specs may carry a colon-delimited parameter (`"decimal:2"`). The resolver splits
on the first colon and dispatches; `decimal:N` quantizes to `Decimal` at scale `N`
(`ROUND_HALF_UP`). The registry-backed named form (`"AsCollection:CustomCollection"`)
is intentionally **not** added — passing the cast class/instance directly covers the
real need without a global name registry (avoids the indirection and a mutable global).
Built-in `_READ_SKIP_CASTS` / `_WRITE_SKIP_CASTS` semantics (e.g. `hashed` write-only,
JSON read-only) are preserved by the resolver.
