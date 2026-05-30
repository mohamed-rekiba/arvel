# ADR-063 — Use Python files as the default translation backend

**Status**: Accepted
**Date**: 2026-05-19
**Decider**: Solution Architect
**Supersedes**: none
**Related**: PRD-015 § 10 Q2, SAD-015 § 3

---

## Context

WI-015's i18n subsystem (15-S3) needs a translation file format. Candidates:

- **Python `.py` files** — module-level `translations: dict[str, str | dict]`. Type-checkable; no extra parser; no escaping rules; arbitrary nesting; works with mypy/pyright. Can be lazy-loaded via `importlib`.
- **YAML** — readable; non-engineers can edit; needs `pyyaml` (already transitive via several deps); has security concerns with `unsafe_load`.
- **JSON** — universal; readable enough; stdlib only; no comments; awkward for long-form strings.
- **gettext `.po` files** — the industry standard for localisation; tooling exists (poedit, Transifex, Crowdin). Needs `polib`. Two-file dance (`.po` + `.mo`).

## Decision

Use **Python `.py` files** as the default translation backend, exposed by
`PythonFileLoader` implementing the `TranslationLoader` Protocol. Files
live at `resources/lang/{locale}/{namespace}.py` and MUST export a
module-level `translations: dict[str, str | dict[str, str | dict]]`.

The `TranslationLoader` Protocol stays open so users can add a custom
loader (gettext, database-backed, etc.) without modifying framework code.

## Rationale

- **Type-checkable** — `mypy --strict` and `pyright --strict` validate the
  `translations` dict shape. Missing keys in nested dicts surface at type-check
  time, not at runtime.
- **No extra parser dep** — stdlib `importlib` does the loading. We already
  pay the price of starting a Python interpreter.
- **No escaping rules** — strings are Python literals; no YAML-vs-JSON-vs-PO
  escape-rule confusion.
- **Arbitrary nesting** — dot-notation lookup (`__("messages.welcome.greeting")`)
  works naturally over nested dicts.
- **Matches the Pydantic-app ethos** — arvel is "Pydantic + types everywhere".
  YAML config is the conventional Laravel choice but a poor Python fit.
- **Reload is cheap** — `importlib.reload(module)` re-runs the file; no parser
  re-instantiation.

## Consequences

### Positive

- Translation files are first-class Python modules; IDE refactor tools work.
- Zero new runtime deps.
- Translators (humans) editing the file get Python syntax highlighting + linting in any IDE.

### Negative

- Non-engineer translators face a Python file (with `{` and `:` and `,`) instead of a friendly `.po` editor. We accept this — arvel's typical user is technical (frameworks are sold to devs).
- Translation files run during import; in theory they can side-effect. We document and lint: `resources/lang/*.py` MUST export only `translations: dict`. Lint rule lands in WI-017.

### Neutral

- For consumers wanting gettext, the door is open: implement `TranslationLoader` and register your loader in `LangServiceProvider`. We don't ship a built-in gettext loader (out of scope per NG6-NG8 family).

## Alternatives rejected

- **YAML** — readable but needs `pyyaml`, no static type checking, security concerns with `unsafe_load` if anyone uses tags.
- **JSON** — too rigid for long-form strings; no comments; explicit escape rules add friction.
- **gettext `.po`/`.mo`** — overkill for the typical Python-app translation need; tooling is heavyweight; we lose static type checking entirely.
- **TOML** — readable but lacks nesting expressiveness; would require explicit grouping syntax that doesn't match dot-notation lookup.

## Implementation notes (for Stage 3b)

```python
# packages/arvel/src/arvel/i18n/loader.py
import importlib
from typing import Protocol

class TranslationLoader(Protocol):
    def load(self, locale: str, namespace: str) -> dict[str, str | dict]: ...

class PythonFileLoader:
    """Default loader. Reads resources/lang/{locale}/{namespace}.py."""

    def __init__(self, base_path: Path) -> None:
        self._base = base_path

    def load(self, locale: str, namespace: str) -> dict[str, str | dict]:
        module_path = f"resources.lang.{locale}.{namespace}"
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            raise TranslationFileMissingError(locale, namespace) from e
        if not hasattr(module, "translations"):
            raise TranslationFileMalformedError(
                f"{module_path} missing required `translations: dict` export"
            )
        return dict(module.translations)
```

## Cross-references

- SAD-015 § 3 Q2
- PRD-015 § 10 Q2, SEC-015-003 (no code-eval on parameter substitution)
- Constitution Article II (Pydantic strict, types everywhere)
