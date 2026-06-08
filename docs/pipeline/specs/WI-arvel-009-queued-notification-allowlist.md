# WI-arvel-009 — Queued notifications must deserialize from an allowlist, not arbitrary imports

| | |
|---|---|
| **Module** | notifications (queue integration) |
| **Complexity** | L2 | **Risk** | Tier 3 (deserialization / security) | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/009-events-notifications.md` (C1 fixed; C2 state-loss + morph/txn/log findings deferred) |
| **Review** | C1 confirmed: only place in the queue layer that bypasses the allowlist trust boundary |

## Problem

`NotificationJob.handle()` resolved the notifiable and notification classes with
`_import_class`, which ran `importlib.import_module()` on dotted paths taken
**directly from the queue payload**:

```python
def _import_class(dotted: str) -> type:
    module_path, _, class_name = dotted.rpartition(".")
    import importlib
    module = importlib.import_module(module_path)   # arbitrary module import
    return getattr(module, class_name)
```

Everywhere else, the queue treats the payload as an untrusted boundary:
`JobRegistry` allowlists job classes, and `ListenerJob` resolves listeners/events
via `EventRegistry`/`ListenerRegistry` (dict lookups, no import). `NotificationJob`
was the lone exception — a tampered or malicious payload (`redis`/`amqp` brokers,
or any non-app producer) could trigger arbitrary module imports, whose
import-time side effects are a code-execution gadget (OWASP A08, insecure
deserialization).

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | A queued notification resolves its notifiable + notification from allowlist registries populated at class definition (no payload import). | `tests/test_notifications/test_channels_and_notifiable_more.py::test_notification_job_resolves_classes_from_registry` | PASS |
| SPEC-2 | A payload referencing an unregistered class is rejected with `UnregisteredNotificationClassError` and the unknown module is never imported. | `tests/test_queue/test_047_queue_reliability.py::TestStory4NotificationJob::test_unregistered_class_is_rejected_without_import` | PASS |
| SPEC-3 | A legitimately-registered notifiable + notification still round-trips through `NotificationJob.handle()` end to end. | `...::TestStory4NotificationJob::test_notification_job_refetches_notifiable_before_delivery` | PASS |
| SPEC-4 | The `Notifiable` registry hook fires through the ORM `Model` MRO without breaking model creation. | full arvel suite (4297 passed) | PASS |
| SPEC-5 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean on changed files. | `mypy` + `pyright` + `ruff` | PASS |

## Root-cause fix

- `notification.py` — `NotificationRegistry` + `Notification.__init_subclass__`
  (mirrors `Event`/`Listener`).
- `notifiable.py` — `NotifiableRegistry` + `Notifiable.__init_subclass__`
  (verified the chain fires for `class X(Model, …, Notifiable)`).
- `notification_job.py` — resolve both classes via `_resolve(registry, key, kind)`;
  removed `_import_class`. A miss raises `UnregisteredNotificationClassError`.
- `exceptions.py` — new `UnregisteredNotificationClassError` with an ops-friendly
  message ("make sure the worker imports the module that defines it").

## Deliberate design decisions

- **Allowlist over import**: registries are populated when the legit class is
  imported (app boot loads models/notifications). The worker only does dict
  lookups — no `importlib` on payload strings. This is the exact pattern the rest
  of the queue already uses.
- **Reject, don't fall back**: an unknown class raises (→ worker DLQs the job)
  rather than silently importing or skipping. Fail loud, fail safe.
- **Test fixture realism**: `_QueuedNotifiable` now subclasses `Notifiable` — a
  queued notifiable always is one, so it self-registers.

## Deferred (tracked)

- **C2 (High)** — queued notifications drop constructor state (`notification_cls()`
  is no-arg). Needs a `Notification` serialization contract (Pydantic base or
  explicit `to_array`/`from_array`).
- **Morph key** — `notifiable_type` stores short `__name__`, not an FQCN/alias
  (collision across modules).
- **Txn boundary** — `DatabaseChannel` commits on its own session (survives a
  rolled-back request transaction).
- **Observability** — `EventDispatcher._dispatch_queued` swallows Bus-dispatch
  errors without logging (comment claims "logged upstream"); should mirror
  `NotificationManager`'s fallback warning.
- **Parity-additive** — wildcard listeners, event subscribers, on-demand/anonymous
  notifications, `markAsRead`/unread queries.
