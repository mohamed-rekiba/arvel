# Epic: Nested / wildcard validation

## Summary
Close the last "more validation rules" item from WI-043: dot-notation and `*`
wildcard field paths in the `rules()` layer. The validator now expands field keys
into concrete data paths instead of treating them as flat dict keys.

**Spec:** `docs/pipeline/specs/WI-arvel-045-nested-wildcard-validation.md`

## Delivered

### Story 1: Dotted nested paths — Done
`address.city` validates the nested value; always yields a target even when the
parent is missing, so `required`/`present` fire.

### Story 2: Wildcards — Done
`items.*.id` validates every list element; dict wildcards (`meta.*.value`) and
explicit indices (`items.0.id`) work too. Wildcards iterate only existing
entries — a missing collection produces no errors.

### Story 3: Path-aware semantics — Done
Errors key by concrete path (`items.1.id`); presence rules see a path-scoped data
view; message/attribute overrides resolve by wildcard or concrete path.

## Tests
`packages/arvel/tests/validation/test_wi045_nested_wildcard.py` — 19 cases.

## Gates
ruff clean; mypy 0 (1067 files); pyright 0/0; validation suite 132 passed.

## Status
This closes the validation parity backlog (WI-044 + WI-045 together cover the
whole "more validation rules" gap).
