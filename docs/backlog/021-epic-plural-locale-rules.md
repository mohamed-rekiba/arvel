# Epic: Positional pluralisation follows the locale plural rule

## Summary
`select_plural_variant` must pick a positional variant via the locale's plural
rule (Laravel's `MessageSelector::getPluralIndex`), not by raw count index, so
`"apple|apples"` returns the singular only at `count == 1` — matching Laravel.

**Module:** i18n · **Spec:** `docs/pipeline/specs/WI-arvel-021-plural-locale-rules.md`

## Stories

### Story 1: positional pipe uses the locale plural rule
**As a** developer calling `trans_choice`/`__choice`, **I want** the two-form
`"singular|plural"` spec to follow the locale's plural rule, **so that**
`count == 1` gives the singular and other counts give the plural, like Laravel.

**Acceptance Criteria**:
- [x] English `"apple|apples"`: count 0→plural, 1→singular, 2+→plural.
- [x] French treats 0 and 1 as singular.
- [x] Russian (Slavic) and Arabic select their >2 forms by count.
- [x] `pt_BR` / `pt-BR` resolve on the `pt` subtag; unknown locale → first form.
- [x] Bracket syntax (`{0}…|[1,4]…`) precedence is unaffected.

### Story 2: Translator threads the active locale
**As a** developer using `Translator.choice`, **I want** the pluraliser to use the
translator's active locale (and any per-call override), **so that** pluralisation
is correct without passing the locale twice.

**Acceptance Criteria**:
- [x] `Translator.choice` passes its current locale into `select_plural_variant`.
- [x] A per-call `locale=` override is honoured.

**Security Requirements**:
- [ ] None (internal formatting helper).

**Documentation Requirements**:
- [x] `localization.md` pluralisation section explains the locale plural rule.
- [x] `select_plural_variant` docstring states the rule-based selection.

**Requirement Refs**: SPEC-1 · **Priority**: Must · **Complexity**: Small · **Status**: Done

## Out of scope (deferred)
- Laravel's bracket-fallthrough quirk (strip conditions, then apply plural index
  when no bracket matches) — Arvel keeps the intuitive default/last behaviour.
