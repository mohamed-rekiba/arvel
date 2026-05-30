# ADR-037: Event is a Pydantic BaseModel

**Status**: Accepted | **Date**: 2026-05-18 | **WI**: arvel-009

## Context

Events need to be serializable for `ShouldQueue` listeners (they travel over the queue as JSON). They should also be typed so listeners can declare `Listener[OrderShipped]` and get IDE autocompletion.

## Decision

`Event` extends `pydantic.BaseModel`. Subclasses declare fields as typed Pydantic attributes.

## Rationale

- Consistent with `Job` (WI-008 ADR-033) — same serialization pattern, same `model_validate_json`
- Zero extra deps — Pydantic is already a core dep
- `model_dump_json()` / `model_validate_json()` gives the `ListenerJob` wire format for free
- `EventRegistry` mirrors `JobRegistry` — populated by `Event.__init_subclass__`

## Consequences

- Event instances are immutable by default (Pydantic `model_config` `frozen=True` preferred)
- Events cannot have non-serializable fields (e.g., open DB connections) — document this constraint
- Validation errors surface at dispatch time, not at construction time — consistent with `Job`
