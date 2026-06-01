# ADR-125 — Stub-template ownership in `make:*` commands

**Status**: Accepted
**Date**: 2026-05-19
**Context**: (Console parity tail)
**Related**: SAD-023 §3.4

## Context

`BaseMakeCommand` currently generates a single generic stub (`class <Name>: pass`) for all `make:*` commands. WI-023 introduces 13 new generators and improves 11 existing ones; users expect each generator to produce framework-aware boilerplate (e.g., `make:controller` should generate a class extending `Controller` with a sample handler).

We had three options:

1. **Per-command override of `_render(name)`** — each subclass owns its template inline.
2. **Template files on disk** — load `.tmpl` files via package data.
3. **Single template engine** — one rendering function that branches by command type.

## Decision

Each `make:*` subclass owns its own `_render(name)` method, returning the stub as a Python string. The base class keeps a fallback (`class <Name>: pass`) but every subclass overrides it.

## Rationale

| Aspect | Per-command override | Template files | Single engine |
|---|---|---|---|
| Type-checked | ✓ | ✗ (strings) | ✗ |
| Co-located with command | ✓ | ✗ (separate dir) | ✗ |
| Testable | ✓ | ✓ | ✓ |
| No package-data complexity | ✓ | ✗ (need `importlib.resources` per stub) | ✓ |
| Easy to add new commands | ✓ (one new file) | ✗ (two: command + template) | ✗ (modify central engine) |
| Easy to add new placeholders | scoped to one command | ✗ (template knows nothing about Python types) | ✗ |

**Per-command override wins** because:

1. Templates are small (typically 10-15 lines). Inline strings stay readable.
2. The template lives next to the command that produces it — easy to locate, easy to test together.
3. Adding a new generator is one new module, no template-file/manifest sync issues.
4. Static type-checking sees the template as code, catching f-string bugs at lint time.

## Consequences

### Positive

- One command per file; template + behavior co-located.
- No `importlib.resources` boilerplate or `MANIFEST.in` updates needed when adding generators.
- Stub renderings can use computed values (timestamps, class names, plural forms) naturally.

### Negative

- Multi-line Python strings have to be carefully formatted. Mitigated by writing tests that snapshot the rendered output (one `tests/console/test_make_stubs.py` per command cluster).

## Alternatives rejected

- **Template files on disk**: requires `MANIFEST.in` and `importlib.resources` plumbing for every generator. Real complexity, no real upside for templates this small.
- **Jinja or other template engine**: massive overkill. We don't need conditionals or loops in stub generation; concatenated f-strings work.

## Implementation notes

- Each subclass overrides `_render(self, name: str) -> str`.
- `_target_subdir` (existing class attribute) determines the output directory.
- For commands that produce timestamped filenames (e.g., `make:migration`), the subclass also overrides `_target_path(self, name: str) -> Path`.
- The base class `_render()` becomes a one-line fallback; if a subclass forgets to override it, the bug is obvious in the generated file.
