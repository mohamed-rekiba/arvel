# WI-arvel-045 — Nested / wildcard validation (`items.*.id`, dotted paths)

- **Module:** 45 (validation — `rules()` layer)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

The last item in the WI-043 "more validation rules" gap. WI-044 deferred this
because it changes the validator's field-iteration model rather than just adding
handlers.

## Scope

`Validator.validate` (`arvel/validation/validator.py`). The handlers in
`rules.py` are untouched — this is purely about how the validator walks fields
and feeds values to those handlers.

## What landed

The validator now treats a field key as a **path**, not a flat dict key.
`resolve_targets(field, data)` expands a (possibly dotted/wildcard) key into a
list of concrete `(path, value, present)` targets, and the validate loop runs
each target's rules independently.

- **Dotted paths** — `address.city` reads `data["address"]["city"]`.
- **Wildcards** — `items.*.id` iterates every element of `items` (lists by index,
  dicts by key) and validates each one's `id`. `meta.*.value` works over dicts.
- **Explicit indices** — `items.0.id` (and negative indices) index into lists.

Two semantics match Laravel:

- A `*` **only iterates entries that exist**. A missing or non-iterable
  collection yields zero targets — no false `required` failures.
- A **non-wildcard nested path always yields one target** even when the parent is
  missing (value `None`, `present=False`), so `required` / `present` fire whether
  `address` is absent or present-without-`city`.

Errors key by the concrete path (`items.1.id`). Custom-message and
attribute-label lookups try the concrete path first, then fall back to the
wildcard form (`items.*.id.required`).

## Design notes

- **Presence is path-aware.** `present` / `filled` / `prohibited` check
  `field in data`. For a nested target the handler gets `field = "items.1.id"`,
  which would never be a flat key — so for nested/wildcard fields the validator
  passes a `_scoped_data` view (the full payload plus the concrete path as a key,
  present only when the leaf exists). Cross-field rules (`same`, `required_with`,
  …) still see the full payload, because top-level siblings remain in it.
- **Backward compatible + zero-copy on the hot path.** A plain field with no `.`
  or `*` resolves to a single `(field, data.get(field), field in data)` target
  and is handed `self._data` directly — identical to the old behavior, no copy.
- **`bail` is per target** — each array element bails independently.
- `object` → `Mapping`/`list` narrowing is cast to concrete element types
  (`Mapping[object, object]` / `list[object]`) so the type checkers stay clean
  without suppressions.

## Tests

`packages/arvel/tests/validation/test_wi045_nested_wildcard.py` — 19 cases:
`resolve_targets` units (plain/dotted/missing/list-wildcard/dict-wildcard/
explicit-index/missing-collection), wildcard validation (each element, all-valid,
type rule, missing array skips), nested validation (missing child, missing
parent, path-aware `present`, `filled` skip), message overrides (wildcard key,
concrete-key-wins), and backward-compat (flat fields, attribute labels).

## Deferred

- None. This closes the validation parity backlog.

## Gates

ruff check + format clean; `uv run mypy` 0 issues (1067 files); `uv run pyright`
0 errors / 0 warnings; validation suite 132 passed.
