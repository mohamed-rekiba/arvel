# Epic: Queued notifications deserialize from an allowlist

## Summary
`NotificationJob` resolved the notifiable and notification classes by running
`importlib.import_module()` on dotted paths taken straight from the queue payload — the
one place in the queue layer that bypassed the allowlist trust boundary used everywhere else
(`JobRegistry`, `ListenerJob`'s `EventRegistry`/`ListenerRegistry`). A tampered payload could
trigger arbitrary module imports (import-time side-effect gadget). The worker now resolves both
classes from registries populated at class definition and rejects unknown classes.

**Module:** notifications · **Spec:** `docs/pipeline/specs/WI-arvel-009-queued-notification-allowlist.md`

## Stories

### Story 1: Queued notifications never import arbitrary classes from the payload
**As a** framework user running a queue worker, **I want** queued notifications resolved from a
known allowlist, **so that** a tampered or malicious queue payload can't make the worker import
arbitrary modules.

**Acceptance Criteria**:
- [x] Given a queued notification, when the worker handles it, then the notifiable and notification classes are resolved from `NotifiableRegistry` / `NotificationRegistry` (populated at class definition) — not by importing the payload's dotted path.
- [x] Given a payload referencing an unregistered class, when the worker handles it, then it raises `UnregisteredNotificationClassError` and the unknown module is never added to `sys.modules`.

**Security Requirements**:
- [x] Closes an insecure-deserialization path (OWASP A08): no `importlib` on untrusted queue payload strings.

**Documentation Requirements**:
- [x] `docs/site/docs/features/notifications.md` explains queued notifications resolve from an allowlist and the worker must import the defining modules.

**Requirement Refs**: SPEC-1, SPEC-2
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Legitimate queued notifications still work
**As an** application developer, **I want** registered notifications and notifiable models to keep
working through the queue, **so that** the security fix changes nothing for correct usage.

**Acceptance Criteria**:
- [x] Given a `Notification` subclass and a `Notifiable` model, when dispatched via the queue, then `NotificationJob.handle()` refetches the notifiable and delivers as before.
- [x] Given the `Notifiable.__init_subclass__` hook, when a model subclasses `Notifiable` through the ORM `Model` MRO, then model creation is unaffected (full suite green).

**Security Requirements**:
- [x] None beyond Story 1.

**Documentation Requirements**:
- [x] Covered by the queued-notifications doc section.

**Requirement Refs**: SPEC-3, SPEC-4
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..008.

## Notes
- The kit doesn't use the notifications subsystem, so this is a framework-correctness/security fix
  with no kit runtime impact.
- Deferred follow-ups (separate work items):
  - **C2** — queued notifications drop constructor state (`notification_cls()` no-arg); needs a `Notification` serialization contract.
  - **Morph key** — `notifiable_type` stores short `__name__`, not FQCN/alias.
  - **Txn boundary** — `DatabaseChannel` commits on its own session (survives request-txn rollback).
  - **Observability** — `EventDispatcher._dispatch_queued` swallows Bus errors without logging.
  - **Parity-additive** — wildcard listeners, subscribers, on-demand/anonymous notifications, unread/markAsRead.
