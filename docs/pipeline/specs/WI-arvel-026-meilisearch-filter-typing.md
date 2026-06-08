# WI-arvel-026 — Meilisearch filters must render by value type (and escape strings)

- **Module**: 26 — arvel-search (`MeilisearchEngine`)
- **Complexity**: L2
- **Risk tier**: 3 (filter-expression injection when values come from request input)
- **Data classification**: internal
- **Status**: completed

## Problem

`MeilisearchEngine.search` quoted every filter value as a string:

```python
body["filter"] = [f'{name} = "{value}"' for name, value in query.filters.items()]
```

Repro — `where("price", 100)`, `where("active", True)`, `where("name", 'a"b')`:

```
['price = "100"', 'active = "True"', 'name = "a"b"']
```

- **C1a (correctness/parity)** — `price = "100"` string-compares a numeric field
  and matches nothing; Laravel Scout emits `price = 100`. Booleans render as
  Python `"True"` (capitalised + quoted) instead of `active = true`.
- **C1b (injection)** — the embedded `"` breaks out of the literal. Filters
  often come from request params, so a crafted value can rewrite or bypass
  another `where` the app added. The SQL engines bind params; only this engine
  string-built filters.

Single root cause: no type handling, no escaping. The Elasticsearch engine is
correct (native values inside a `term` query), so this is Meilisearch-only.

## Fix

`_filter_clause(value)` renders by type and escapes strings:

```python
def _filter_clause(value: object) -> str:
    if value is None:
        return "IS NULL"
    if isinstance(value, bool):
        return f"= {'true' if value else 'false'}"
    if isinstance(value, (int, float)):
        return f"= {value}"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'= "{escaped}"'
```

`bool` is checked before `int` (it's an `int` subclass). Result:
`['price = 100', 'active = true', 'size = 4.5', 'name = "a\"b"', 'note IS NULL']`.

## Acceptance criteria

- Numeric and float filters render bare (`price = 100`, `size = 4.5`).
- Boolean filters render bare lowercase (`active = true` / `= false`), not `"True"`.
- `None` renders `IS NULL`.
- String filters are quoted with `"` and `\` escaped.
- mypy --strict, pyright, ruff check + format clean; arvel-search suite green.

## Out of scope (deferred)

- `should_be_searchable()` conditional indexing (remove-on-save when false).
- Soft-delete `__soft_deleted` indexing, `whereIn`/range filters.
- Chunked `make_all_searchable` import (loads all rows at once — scale, not correctness).

## Files

- `packages/arvel-search/src/arvel_search/engines/meilisearch.py`
- `packages/arvel-search/tests/test_engines.py` (2 new Meilisearch filter cases)
- `docs/site/docs/packages/search.md` (note: `where` filters keep their type / escaped)
