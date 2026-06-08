# WI-arvel-035 — Raw model returns leak `__hidden__` when nested in a dict/list/tuple

- **Module:** 35 (routing / HTTP response normalization)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** confidential (touches password hashes / tokens)
- **Status:** completed
- **Follow-up to:** WI-arvel-032 (raw model return honours `__hidden__`)

## Problem

`_coerce_models_in_result` (in `routing.py`) only handled two shapes: a top-level
`Model` and a top-level `list` of models. A handler that returned a model nested in
a dict — `return {"user": user}` — or a list inside a dict, or a tuple, bypassed the
normalizer entirely. FastAPI then encoded the raw dataclass, leaking every column,
including ones marked `__hidden__` (password hashes, remember tokens).

This is the leak WI-032 was meant to close, just one nesting level deeper. A09 /
sensitive-data exposure, and a Laravel-parity gap (`return ['user' => $user]` hides
hidden attributes in Laravel).

## Fix

Make `_coerce_models_in_result` recurse. A local `coerce()` walks the return value:

- `Model` → `to_dict()` (honours `__hidden__` / `__visible__` / `__appends__`)
- `dict` → rebuild with each value coerced
- `list` → coerce each item
- `tuple` → coerce each item, stay a tuple
- everything else (Pydantic models, `Response`, primitives) → untouched

`to_dict()` reads columns only, so the result is already plain — no infinite
recursion, no async relation loads.

## Tests

`packages/arvel/tests/routing/test_wi054_hidden_field_leak.py`:

- `test_models_nested_in_dict_hide_hidden_columns` — model in a dict value, in a
  list inside a dict, and in a nested dict all drop `secret`.
- Existing top-level model / list / non-model / Pydantic passthrough tests still pass.

## Gates

ruff check + format clean; mypy 0 issues (1065 files); pyright 0 errors/0 warnings;
WI-054 routing suite 5 passed.
