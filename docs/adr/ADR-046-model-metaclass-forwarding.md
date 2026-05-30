# ADR-046: Model Class-Level QB Forwarding via Metaclass

**Status**: Accepted
**Date**: 2026-05-18

## Decision

Add `_ModelMeta(DeclarativeAttributeIntercept)` to `Model`. Its `__getattr__` forwards unknown class-level attribute accesses to `cls.query()`.

## Context

Laravel's Eloquent allows `User::where(...)` directly on the model class via PHP's `__callStatic`. Without an equivalent, arvel requires `User.where(...)` — a visible ergonomic gap.

## Options

**A. Explicit method list** — add `where`, `find`, `order_by`, etc. as `@classmethod` wrappers. Maintenance burden: every new QB method needs a parallel classmethod.

**B. `__init_subclass__` loop** — iterate over QB methods and inject classmethods at subclass definition time. Fragile: captures QB methods at class definition, not at call time; doesn't handle methods added later.

**C. Metaclass `__getattr__`** ← chosen. Fires only for missing names; zero maintenance; type-safe with proper stubs.

## Consequences

- `User.where(...)`, `User.order_by(...)`, `User.with_("posts")` all work without `.query()`
- `User.find(1)`, `User.create({...})`, `User.query()` remain explicit classmethods (take precedence over `__getattr__`)
- `pyright --strict` requires a stub or `# type: ignore` comment at the `metaclass=_ModelMeta` line due to SQLAlchemy's internal typing — acceptable, isolated to one line
