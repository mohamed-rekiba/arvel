# WI-arvel-044 — Validation parity round 2 (bail, conditional presence, dates, custom rules, Rule builders)

- **Module:** 44 (validation — `rules()` layer)
- **Complexity:** L2
- **Risk tier:** 2
- **Data classification:** internal
- **Status:** completed

This is a feature-parity work item, not a defect fix — gap #4 from the WI-043
triage, picked first because it's additive and low risk (no change to existing
rule behavior).

## Scope

The string-rule validation layer in `arvel/validation/`: the `Validator` loop
(`validator.py`), the rule handlers and registry (`rules.py`), and the `Rule`
builder helpers (`rule.py`). The `sometimes` / `Rule.sometimes` conditional path
already shipped, so it's out of scope here.

## What landed

**Flow control — `bail`.** The validator now stops running a field's remaining
rules at the first failure when `bail` appears in that field's chain. It's
detected per field, the `bail` token itself never produces an error, and it only
affects the field it's on. Without `bail` the loop still collects every failure
(unchanged).

**Conditional presence.** Six rules that make a field required based on other
fields, failing only when the trigger condition holds *and* the field is empty:

- `required_if:other,val,...` / `required_unless:other,val,...`
- `required_with:f1,...` / `required_with_all:f1,...`
- `required_without:f1,...` / `required_without_all:f1,...`

"Present" follows Laravel's notion: the other key exists with a non-empty value.

**Dates.** `date`, `date_format:FMT`, and four comparisons —
`before` / `after` / `before_or_equal` / `after_or_equal`. Bounds accept a
literal date, another field name, or `today` / `now`. Inputs accept ISO-8601
strings and `date` / `datetime` objects. Naive values are normalized to UTC so
every comparison is between aware datetimes (consistent ordering, and no
tz-naive lint debt).

**Custom rules.** `register_rule(name, handler)` (exported from
`arvel.validation`) adds a handler to the shared registry. Handlers take
`(field, value, params, data, request)` and return a message or `None`, sync or
async — same contract as the built-ins.

**Rule builders.** `Rule.in_`, `Rule.not_in`, `Rule.exists`, `Rule.unique`
(with `ignore=` / `id_column=`), `Rule.required_if`, `Rule.required_unless`.
They emit the same rule-expression strings the parser already understands, so
they slot straight into a `rules()` dict.

## Design notes

- All new rules are no-ops on `None` (except the conditional-presence ones,
  whose whole job is to react to emptiness), so they layer cleanly with
  `nullable` like the existing rules.
- `_date_comparison` takes a small frozen `_DateCmp(rule, compare, message)`
  spec rather than four loose params — keeps the per-rule wrappers one-liners and
  the arg count within limits.
- Builders comma-join their values, so a value containing a comma isn't
  supported — that case wants a custom rule. Documented.

## Deferred

- **Nested / wildcard rules** (`items.*.id`). This changes the validator's
  field-iteration model (it has to expand wildcard paths against the payload
  before applying rules), so it's its own work item. It's the last remaining
  entry under "More validation rules" in the CHANGELOG.

## Tests

`packages/arvel/tests/validation/test_wi044_validation_parity.py` — 27 cases:
`bail` (stop-at-first, collect-all without it, pass path), `required_if` /
`required_unless` (trigger + skip), `required_with` / `with_all` / `without` /
`without_all`, date rules (ISO + `date` object, garbage rejection, `date_format`
match/miss, before/after literals + field-ref bound, `*_or_equal` boundary),
custom `register_rule` round-trip, and every `Rule` builder (string output +
running the output through the validator).

## Gates

ruff check + format clean; `uv run mypy` 0 issues (1066 files); `uv run pyright`
0 errors / 0 warnings; validation suite 113 passed; `mkdocs build --strict`
clean.
