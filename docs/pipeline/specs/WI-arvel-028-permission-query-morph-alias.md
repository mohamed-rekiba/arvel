# WI-arvel-028 — Role/permission query helpers must match the morph-alias discriminator

- **Module**: 28 — arvel-permission (`HasRoles` / `HasPermissions` class-method query helpers)
- **Complexity**: L2
- **Risk tier**: 2 (correctness; A01-adjacent — feeds wrong sets into admin/bulk tooling)
- **Data classification**: internal
- **Status**: completed

## Problem

`MorphToMany` writes the pivot's `model_type` discriminator as
`get_morph_alias(type(owner))`, whose resolution is: `__morph_class__` override →
registered `morph_map` alias → short class name (`cls.__name__`).

The four class-level query helpers filtered on the short class name instead:

```python
model_has_roles.c.model_type == cls.__name__
```

So whenever an app registers a `morph_map` or sets `__morph_class__` (the
recommended setup — and mandatory under `require_morph_map()`), the stored token
(e.g. `"user"`) never equals `cls.__name__` (`"User"`), and the helpers silently
mismatch every row:

- `query_with_role` / `query_with_permission` → return `[]` even when holders exist.
- `query_without_role` / `query_without_permission` → return **everyone**
  (the `~pk.in_(empty_subquery)` excludes nobody), including users who actually
  hold the role/permission. Feeding that into a bulk admin action is the
  A01-adjacent risk.

Instance checks (`has_role`, `has_permission_to`) were always correct — they read
through the `MorphToMany` accessor, which uses the same alias on read and write.

## Repro

Register `morph_map({"m_quser": _MQUser})`, assign a role, then:

- stored pivot row: `model_type = 'm_quser'`
- `has_role(instance)` → `True`
- `query_with_role(...)` → `[]` (filtered `'_MQUser'`)

## Fix

Resolve the same token the pivot stores in all four helpers:

```python
model_has_roles.c.model_type == get_morph_alias(cls)
```

(and the matching `model_has_permissions` filters).

## Acceptance criteria

- Under a registered morph map, `query_with_role`/`query_with_permission` return
  exactly the holders; `query_without_*` return exactly the non-holders.
- The default (no morph map) case is unchanged — `get_morph_alias` falls back to
  the short class name.
- ruff check + format, mypy (`-p arvel_permission`), pyright clean; package suite green.

## Out of scope (reviewed, no change)

- `matches_wildcard` is more restrictive than Spatie for implied sub-parts
  (fail-safe; not a bypass). Guard scoping in `_perm_matches`/`has_role` correct.
- `register_permissions_with_gate` before-hook returns `True`/`None` only (never
  `False`), so a missing permission falls through to policies — correct.
- arvel-audit redaction (`__audit_redact__`/`__audit_exclude__` applied on every
  create/update/delete path) and arvel-image hardening (filename sanitization,
  content-based MIME, decompression-bomb ceiling) reviewed clean.

## Files

- `packages/arvel-permission/src/arvel_permission/traits.py`
- `packages/arvel-permission/tests/test_052_query_morph_alias.py` (new)
