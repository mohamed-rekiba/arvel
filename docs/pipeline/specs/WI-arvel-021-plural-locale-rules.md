# WI-arvel-021 — Positional pluralisation must follow the locale plural rule

- **Module**: 21 — i18n / translation (`select_plural_variant`, `Translator.choice`)
- **Complexity**: L2
- **Risk tier**: 2
- **Data classification**: internal
- **Status**: completed

## Problem

The positional pipe path (`"apple|apples"`) picked a variant by **raw count
index** instead of the locale's plural rule:

```python
if count < len(variants):
    idx = count       # count 0 -> idx 0, count 1 -> idx 1, ...
else:
    idx = len(variants) - 1
```

- **C1 (correctness / Laravel parity)** — the standard two-form call returned the
  wrong form for the two most common counts. Laravel's
  `MessageSelector::getPluralIndex` for English picks the singular only at
  `count == 1` (index 0) and the plural for everything else (index 1).

### Repro (pre-fix)

```python
select_plural_variant("apple|apples", count=1, replace={})  # -> "apples"  (expected "apple")
select_plural_variant("apple|apples", count=0, replace={})  # -> "apple"   (expected "apples")
```

`trans_choice('messages.apples', 1)` — the single most common pluralisation call
— returned the plural. The docs even claimed `count=1 # "1 apple"`, so the code
contradicted its own documented intent.

## Fix

Port Laravel's `getPluralIndex` and route the positional path through it,
threading the active locale from `Translator.choice`:

```python
idx = _plural_index(locale, count)        # English: 0 if count == 1 else 1
if idx >= len(variants):
    idx = len(variants) - 1
return _substitute(variants[idx], count=count, replace=replace)
```

`_plural_index` is a flat dispatch table of small per-family rule functions
(zero-form, two-form, zero-or-one, Slavic, Czech, Polish, Arabic, …) keyed by
the language subtag (`pt` from `pt_BR`). Unknown locales fall back to index 0.
The bracket path (`{0}…|[1,4]…`) is unchanged — explicit conditions still win.

## Acceptance criteria

- English `"apple|apples"`: count 0→plural, 1→singular, 2+→plural.
- French treats 0 and 1 as singular; Russian/Arabic select their >2 forms.
- `pt_BR` / `pt-BR` resolve on the `pt` subtag; unknown locale → first form.
- `Translator.choice` uses its active locale and honours a per-call override.
- Bracket syntax precedence unaffected.
- mypy --strict, pyright, ruff check, ruff format clean; full arvel suite green.

## Out of scope (deferred)

- Laravel's bracket-fallthrough quirk (stripping conditions then applying the
  plural index when no bracket matches) — Arvel keeps the more intuitive
  default/last behaviour, which passing bracket tests already encode.
- Per-call locale plumbing into the bare `select_plural_variant` for callers that
  bypass `Translator` — they can pass `locale=` explicitly.

## Files

- `packages/arvel/src/arvel/i18n/pluralisation.py`
- `packages/arvel/src/arvel/i18n/translator.py`
- `packages/arvel/tests/i18n/test_choice.py` (updated to Laravel contract)
- `packages/arvel/tests/i18n/test_wi_021_plural_rules.py` (new)
- `pyproject.toml` (per-file PLR2004/ARG001 ignore for the CLDR rule table)
