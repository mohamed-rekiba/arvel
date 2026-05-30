# ADR-050: Collection[T] Is a list[T] Subclass

**Status**: Accepted
**Date**: 2026-05-18

## Decision

`Collection[T]` inherits from `list[T]`. All existing code that type-hints or calls `isinstance(result, list)` continues to work without modification.

## Context

Arvel's QB currently returns `list[T]`. Adding Laravel-style collection methods (`map`, `filter`, `pluck`, `group_by`, etc.) requires a richer type. Two paths exist.

## Options

**A. Wrapper class** — `Collection[T]` holds an internal `list[T]` and does NOT inherit from `list`. Clean OOP design but breaks all existing callers that use `list` type hints or `isinstance(..., list)`.

**B. `list[T]` subclass** ← chosen. `isinstance(collection, list)` returns `True`. All `list` methods are available. Chainable methods return `Collection` instances. Zero migration cost.

## Tradeoffs

- Subclassing `list` has subtle Python gotchas (e.g., `list.copy()` returns a `list`, not `Collection`). Affected built-in methods are overridden to return `Collection` where needed.
- `mypy --strict` handles `list` subclasses correctly when `Generic[T]` is explicitly declared.
- Performance: no overhead over a plain list for existing callers.
