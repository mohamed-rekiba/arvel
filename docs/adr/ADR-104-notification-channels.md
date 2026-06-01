# ADR-104: Notification Channels — mail + database + log + broadcast stub

**Status**: Accepted | **Date**: 2026-05-18 | **WI**: arvel-009

## Context

`Notification` must support multiple delivery channels. The full set (mail, database, broadcast, slack, vonage, webhook) is too large for one WI.

## Decision

Ship four channels in WI-009: `mail`, `database`, `log`, `broadcast` (stub). Remaining channels follow in later WIs.

## Rationale

- **mail + database** cover ~90% of real-world use cases (email + in-app notification center)
- **log** is free (structlog is a core dep) and essential for local dev/test
- **broadcast stub** keeps the interface complete so callers specifying `via = ["mail", "broadcast"]` don't crash — they get a logged warning
- Slack/Vonage/webhook each require new optional deps; deferring keeps this WI focused

## Consequences

- Developers using `broadcast` channel will get a warning in WI-009; fully functional in WI-010
- Channel interface (`MailChannel`, `DatabaseChannel`, etc.) must remain stable — adding Slack in WI-010 must not change the protocol
- `NotificationManager._resolve_channel(name)` raises `UnknownChannelError` for unregistered names (not silently skipped)
