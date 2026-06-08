# WI-arvel-018 — config dict segments must be key-only lookups

- **Module**: 18 — config (dotted-key registry)
- **Complexity**: L2
- **Risk tier**: 2
- **Data classification**: internal
- **Status**: completed

## Problem

`_lookup_registry.lookup()` traversed each dotted segment by trying **attribute
access first**, falling back to dict subscript only when the attribute was
absent. For a dict cursor, a segment that is missing as a key but shares a name
with a dict builtin (`get`, `items`, `keys`, `values`, `pop`, `popitem`,
`copy`, `update`, `clear`, `setdefault`, `fromkeys`) resolved to the **bound
method** instead of missing.

- **C1 (correctness)** — `config("cache.stores.get", "x")` returned
  `dict.get` instead of `"x"`; `lookup("cache.stores.get")` returned the method
  instead of raising `ConfigKeyError`. Breaks the `config(key, default)`
  contract and diverges from Laravel, where config arrays are pure key lookups.

### Repro (pre-fix)

```python
register("cache", types.SimpleNamespace(stores={"redis": {"host": "localhost"}}))
config("cache.stores.get", "FALLBACK")   # -> <built-in method get ...>
lookup("cache.stores.get")               # -> <built-in method get ...> (no raise)
```

## Fix

In `lookup()`, branch on the cursor type during traversal:

- **dict** → look the segment up as a key only; raise `ConfigKeyError` on a
  miss. Never fall through to attribute access.
- **module / namespace / object** → attribute access (unchanged), so top-level
  registry entries and `SimpleNamespace` cache snapshots still resolve.

## Acceptance criteria

- Real nested dict keys still resolve (`cache.stores.redis.host`).
- A missing plain key returns the supplied default.
- Every dict-builtin name as a missing key returns the default (`config`) and
  raises `ConfigKeyError` (`lookup`) — no bound method leaks.
- Attribute access on namespaces/modules still works at any depth.
- mypy --strict, pyright, ruff check, ruff format clean; full arvel suite green.

## Out of scope (deferred)

- URL-embedded credentials in `config:cache` output are not redacted (documented
  limitation in `_strip_secrets`; keep secrets in discrete keys).
- No array-set form of `config()`; runtime config is read-only by design.
- `env()` type-driven coercion vs Laravel string coercion — deliberate.

## Files

- `packages/arvel/src/arvel/config/_lookup_registry.py`
- `packages/arvel/tests/config/test_wi_018_dict_key_shadowing.py` (new)
- `docs/site/docs/core-concepts/configuration.md`
