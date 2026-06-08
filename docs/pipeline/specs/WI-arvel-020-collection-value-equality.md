# WI-arvel-020 — Collection.intersect / diff must compare by value

- **Module**: 20 — support helpers (`Collection`)
- **Complexity**: L2
- **Risk tier**: 2
- **Data classification**: internal
- **Status**: completed

## Problem

`Collection.intersect` and `Collection.diff` compared elements by **object
identity** (`id()`), not value (`==`):

```python
other_ids = {id(x) for x in other}
return Collection(item for item in self if id(item) in other_ids)
```

- **C1 (correctness)** — value-equal-but-distinct objects (dicts, dataclasses,
  Pydantic/ORM models, runtime-built strings, large ints) never matched.
  Inconsistent with the sibling `only`/`except_` (which use `==`) and with
  Laravel's value-based `intersect`/`diff`.

### Repro (pre-fix)

```python
Collection([{"id": 1}, {"id": 2}]).intersect([{"id": 2}])  # -> [] (expected [{"id":2}])
Collection([{"id": 1}, {"id": 2}]).diff([{"id": 2}])       # -> [{"id":1},{"id":2}] (expected [{"id":1}])
```

## Fix

Match by value, consistent with `only`/`except_`:

```python
def intersect(self, other): return Collection(i for i in self if i in other)
def diff(self, other):      return Collection(i for i in self if i not in other)
```

`in` uses `==`, works for unhashable members, and matches Laravel.

## Acceptance criteria

- `intersect`/`diff` match value-equal dicts and runtime-built strings.
- `intersect`/`diff` agree with `only`/`except_` on the same inputs.
- Plain-`object()` cases still behave (identity coincides with `==`).
- mypy --strict, pyright, ruff check, ruff format clean; full arvel suite green.

## Out of scope (deferred)

- `Str.limit` not `rtrim`-ing before `end`; `Str.slug` missing `@ → at`
  dictionary; `Arr.get`/`has` not traversing numeric list indices — all minor
  parity, additive.

## Files

- `packages/arvel/src/arvel/support/collections.py`
- `packages/arvel/tests/support/test_wi_020_collection_value_equality.py` (new)
