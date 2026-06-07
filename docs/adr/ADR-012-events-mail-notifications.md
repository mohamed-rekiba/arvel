# ADR-012 — Events, Mail & Notifications

**Status**: Accepted
**Date**: original decisions 2026-06-07 – 2026-06-07; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Events as Pydantic BaseModel, Mailable ABC design, notification channel set.

## Why this is one ADR

Three small subsystems with the same shape — Pydantic-backed message types dispatched through a thin runtime. One ADR avoids three near-empty files.

---

## § 1 — Event is a Pydantic BaseModel

**Originally**: ADR-102 · Status: Accepted | **Date**: 2026-05-18 | **WI**: arvel-009

### Context

Events need to be serializable for `ShouldQueue` listeners (they travel over the queue as JSON). They should also be typed so listeners can declare `Listener[OrderShipped]` and get IDE autocompletion.

### Decision

`Event` extends `pydantic.BaseModel`. Subclasses declare fields as typed Pydantic attributes.

### Rationale

- Consistent with `Job` (WI-008 ADR-011 § 1) — same serialization pattern, same `model_validate_json`
- Zero extra deps — Pydantic is already a core dep
- `model_dump_json()` / `model_validate_json()` gives the `ListenerJob` wire format for free
- `EventRegistry` mirrors `JobRegistry` — populated by `Event.__init_subclass__`

### Consequences

- Event instances are immutable by default (Pydantic `model_config` `frozen=True` preferred)
- Events cannot have non-serializable fields (e.g., open DB connections) — document this constraint
- Validation errors surface at dispatch time, not at construction time — consistent with `Job`

---

## § 2 — Mailable is an ABC (not Pydantic BaseModel)

**Originally**: ADR-103 · Status: Accepted | **Date**: 2026-05-18 | **WI**: arvel-009

### Context

`Mailable` must define email structure (from/to/subject/body). Unlike `Job` and `Event`, mailables are not serialized over a queue — they are rendered and sent synchronously or via a notification channel.

### Decision

`Mailable` is an abstract class (ABC) with three abstract methods: `envelope()`, `content()`, `attachments()`.

### Rationale

- Mailables often hold constructor-injected objects (e.g., a `User` ORM instance) that are not JSON-serializable
- The rendering pipeline is sync: `envelope()` + `content()` + Jinja2 render → driver send
- No need for `model_dump`/`model_validate` — the driver only needs the rendered text
- Laravel's `Mailable` is also a class with methods, not a data bag

### Consequences

- Mailables cannot be put directly on the queue (developers should create a `Job` that constructs and sends the mailable)
- If queued mail is needed, a `SendMailJob(mailable_class, payload)` pattern is the recommended approach (future WI)
- Type safety maintained via `@abstractmethod` enforced by mypy/pyright

---

## § 3 — Notification Channels — mail + database + log + broadcast stub

**Originally**: ADR-104 · Status: Accepted | **Date**: 2026-05-18 | **WI**: arvel-009

### Context

`Notification` must support multiple delivery channels. The full set (mail, database, broadcast, slack, vonage, webhook) is too large for one WI.

### Decision

Ship four channels in WI-009: `mail`, `database`, `log`, `broadcast` (stub). Remaining channels follow in later WIs.

### Rationale

- **mail + database** cover ~90% of real-world use cases (email + in-app notification center)
- **log** is free (structlog is a core dep) and essential for local dev/test
- **broadcast stub** keeps the interface complete so callers specifying `via = ["mail", "broadcast"]` don't crash — they get a logged warning
- Slack/Vonage/webhook each require new optional deps; deferring keeps this WI focused

### Consequences

- Developers using `broadcast` channel will get a warning in WI-009; fully functional in WI-010
- Channel interface (`MailChannel`, `DatabaseChannel`, etc.) must remain stable — adding Slack in WI-010 must not change the protocol
- `NotificationManager._resolve_channel(name)` raises `UnknownChannelError` for unregistered names (not silently skipped)

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-102 | — | Event is a Pydantic BaseModel | § 1 |
| ADR-103 | — | Mailable is an ABC (not Pydantic BaseModel) | § 2 |
| ADR-104 | — | Notification Channels — mail + database + log + broadcast stub | § 3 |
