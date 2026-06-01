# arvel-audit

<a name="introduction"></a>
## Introduction

`arvel-audit` provides two logging layers for compliance and history:

- **Audit trail** — mix `Auditable` into a model and every create/update/delete writes an `AuditEntry` in the same transaction.
- **Activity log** — record business events with the fluent `activity()` API, modeled after Spatie's Laravel ActivityLog.

<a name="installation"></a>
## Installation

```bash
uv add "arvel[audit]"
```

Register the provider and publish the migrations:

```python
# bootstrap/providers.py
from arvel_audit import AuditServiceProvider

providers = [AuditServiceProvider]
```

```bash
arvel vendor:publish --tag=arvel-audit   # or: arvel audit:install
arvel migrate
```

The migrations create `audit_entries` and `activity_entries`. The provider binds `AuditConfig` and wires the `Auditable` observers on boot.

<a name="auditing-model-changes"></a>
## Auditing Model Changes

```python
from arvel.database import Model, id_, string
from arvel_audit import Auditable, AuditLog


class Order(Model, Auditable):
    __tablename__ = "orders"
    id: int = id_()
    status: str = string(20, default="new")
```

Saves now record automatically:

```python
order = Order(status="new")
await order.save()          # writes an AuditEntry, action="created"

order.status = "paid"
await order.save()          # writes an AuditEntry, action="updated"
```

Control which columns are recorded:

```python
class Order(Model, Auditable):
    __audit_redact__ = ("card_number",)   # stored as "***"
    __audit_exclude__ = ("updated_at",)   # left out entirely
```

The actor is read from request context — set `user_id` (the auth middleware does this for you) and it lands in `AuditEntry.actor_id`.

<a name="reading-the-audit-trail"></a>
## Reading the Audit Trail

```python
history = await AuditLog(session).for_model(order).get()
recent = await (
    AuditLog(session)
    .by_actor("alice")
    .action("updated")
    .since(some_datetime)
    .paginate(per_page=15, page=1)
)
```

`AuditLog` filters: `for_model`, `by_actor`, `action`, `since`, `until`; terminals `get`, `first`, `count`, `paginate`.

<a name="activity-log"></a>
## Activity Log

For business events that aren't a single model change:

```python
from arvel_audit import activity, ActivityQuery

await (
    activity("orders", session=session)
    .log("Order exported")
    .by(current_user)
    .on(order)
    .with_properties({"format": "pdf"})
    .save()
)

entries = await ActivityQuery(session).for_subject(order).get()
```

`ActivityQuery` filters: `in_log`, `for_subject`, `by_causer`; terminals `get`, `first`, `count`.

<a name="configuration"></a>
## Configuration

| Env var | Default | Effect |
|---|---|---|
| `AUDIT_ENABLED` | `true` | When false, skips all automatic audit writes |
| `AUDIT_ENCRYPT_VALUES` | `false` | Encrypts `old_values` / `new_values` with the app encrypter |

> [!WARNING]
> `AUDIT_ENCRYPT_VALUES` is read when `arvel_audit`'s models are imported and fixes the column type then, so set it in the environment before the app boots. Encryption needs `APP_KEY` (`arvel key:generate`).

<a name="gotchas"></a>
## Gotchas

- `ActivityQuery` has no `paginate` — only `AuditLog` does.
- `__audit_exclude__` works but isn't covered by the package's own tests.
