# ADR-038: Mailable is an ABC (not Pydantic BaseModel)

**Status**: Accepted | **Date**: 2026-05-18 | **WI**: arvel-009

## Context

`Mailable` must define email structure (from/to/subject/body). Unlike `Job` and `Event`, mailables are not serialized over a queue — they are rendered and sent synchronously or via a notification channel.

## Decision

`Mailable` is an abstract class (ABC) with three abstract methods: `envelope()`, `content()`, `attachments()`.

## Rationale

- Mailables often hold constructor-injected objects (e.g., a `User` ORM instance) that are not JSON-serializable
- The rendering pipeline is sync: `envelope()` + `content()` + Jinja2 render → driver send
- No need for `model_dump`/`model_validate` — the driver only needs the rendered text
- Laravel's `Mailable` is also a class with methods, not a data bag

## Consequences

- Mailables cannot be put directly on the queue (developers should create a `Job` that constructs and sends the mailable)
- If queued mail is needed, a `SendMailJob(mailable_class, payload)` pattern is the recommended approach (future WI)
- Type safety maintained via `@abstractmethod` enforced by mypy/pyright
