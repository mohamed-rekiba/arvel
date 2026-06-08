# Epic: Validation parity round 2

## Summary
Close the bulk of the "More validation rules" feature gap from WI-043. Adds
`bail`, the conditional-presence family, date rules, custom-rule registration,
and `Rule` builders to the `rules()` layer — all additive, no change to existing
rule behavior. Only nested/wildcard support is left for a follow-up.

**Spec:** `docs/pipeline/specs/WI-arvel-044-validation-parity-round-2.md`
**Analysis:** `.context/research/044-validation-parity-round-2.md`

## Delivered

### Story 1: `bail` flow control — Done
Stop a field's rule chain at the first failure. Detected per field; the token
never errors; other fields unaffected.

### Story 2: Conditional presence — Done
`required_if`, `required_unless`, `required_with`, `required_with_all`,
`required_without`, `required_without_all`. Fail only when the trigger holds and
the field is empty.

### Story 3: Date rules — Done
`date`, `date_format:FMT`, `before`, `after`, `before_or_equal`,
`after_or_equal`. Bounds: literal date, another field, or `today`/`now`. Inputs:
ISO strings and `date`/`datetime`. Naive values read as UTC.

### Story 4: Custom rules — Done
`register_rule(name, handler)` exported from `arvel.validation`. Same handler
contract as built-ins (sync or async).

### Story 5: `Rule` builders — Done
`Rule.in_`, `not_in`, `exists`, `unique` (with `ignore`/`id_column`),
`required_if`, `required_unless` — emit rule strings the parser already accepts.

## Remaining (own WI)

### Story 6: Nested / wildcard validation — Backlog
Array-of-objects rules like `items.*.id`. Deferred because it changes the
validator's field-iteration model (wildcard paths must be expanded against the
payload before rules apply). This is the last "More validation rules" item.

## Tests
`packages/arvel/tests/validation/test_wi044_validation_parity.py` — 27 cases.

## Gates
ruff clean; mypy 0 (1066 files); pyright 0/0; validation suite 113 passed;
mkdocs `--strict` clean.
