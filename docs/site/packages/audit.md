# arvel-audit

<a name="introduction"></a>
## Introduction

`arvel-audit` provides two logging layers for compliance and history:

- **Audit trail** — mix `Auditable` into a model and every create/update/delete writes an `AuditEntry` in the same transaction.
- **Activity log** — record business events with the fluent `activity()` API. Attach actor, subject, causer, and arbitrary properties.

<a name="a-quick-tour"></a>
## A Quick Tour

```bash
uv add "arvel[audit]"
arvel audit:install
arvel migrate
```

```python
from arvel.database import Model, id_, string
from arvel_audit import Auditable


class Order(Model, Auditable):
    __tablename__ = "orders"
    id: int = id_()
    status: str = string(20, default="new")
```

```python
order = Order(status="new")
await order.save()          # AuditEntry, action="created"

order.status = "paid"
await order.save()          # AuditEntry, action="updated", old/new values

history = await AuditLog(session).for_model(order).get()
```

For events that aren't a single column change:

```python
from arvel_audit import activity

await (
    activity("orders", session=session)
    .log("Order exported")
    .by(current_user)
    .on(order)
    .with_properties({"format": "pdf"})
    .save()
)
```

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

Saves now record automatically — inside the **same transaction** as the model change:

```python
order = Order(status="new")
await order.save()          # writes an AuditEntry, action="created"

order.status = "paid"
await order.save()          # writes an AuditEntry, action="updated"

await order.delete()        # writes an AuditEntry, action="deleted"
```

Updates only log columns that actually changed. A save with no dirty attributes writes no update entry.

Control which columns are recorded:

```python
class Order(Model, Auditable):
    __audit_redact__ = ("card_number",)   # stored as "***" in old/new values
    __audit_exclude__ = ("updated_at",)   # left out entirely
```

The actor is read from request context — set `user_id` (the auth middleware does this for you) and it lands in `AuditEntry.actor_id`:

```python
# Context.get("user_id") → AuditEntry.actor_id
```

When the subject model is also `Auditable`, properties passed to the activity log automatically strip keys listed in `__audit_redact__` — redacted columns never bleed into activity payloads.

<a name="reading-the-audit-trail"></a>
## Reading the Audit Trail

`AuditLog` is a fluent query over `audit_entries`. Pass the same session you're reading with:

```python
from arvel_audit import AuditLog

history = await AuditLog(session).for_model(order).get()

recent = await (
    AuditLog(session)
    .by_actor(user.id)
    .action("updated")
    .since(some_datetime)
    .until(other_datetime)
    .paginate(per_page=15, page=1)
)

count = await AuditLog(session).for_model(order).count()
first = await AuditLog(session).for_model(order).first()
```

`AuditLog` filters: `for_model`, `by_actor`, `action`, `since`, `until`; terminals `get`, `first`, `count`, `paginate`.

Valid `action` values are `"created"`, `"updated"`, `"deleted"` — anything else raises `InvalidAuditAction`.

> [!NOTE]
> `AuditLog` returns unredacted history from the database. Access control — who may read the trail — is your application's job.

<a name="activity-log"></a>
## Activity Log

For business events that aren't a single model change — exports, invitations, workflow steps — use the fluent activity recorder:

```python
from arvel_audit import activity, ActivityQuery

entry = await (
    activity("orders", session=session)
    .log("Order exported")
    .by(current_user)
    .on(order)
    .with_properties({"format": "pdf", "recipient": "finance@example.com"})
    .save()
)

entries = await ActivityQuery(session).for_subject(order).get()
by_user = await ActivityQuery(session).by_causer(current_user).get()
exports = await ActivityQuery(session).in_log("orders").get()
```

`ActivityQuery` filters: `in_log`, `for_subject`, `by_causer`; terminals `get`, `first`, `count`.

Split logs by name so admin actions and customer actions don't share one bucket:

```python
await activity("admin", session=session).log("Role granted").by(admin).save()
await activity("billing", session=session).log("Invoice sent").by(system_user).save()
```

<a name="disabling-audit"></a>
## Disabling Audit

Turn off automatic writes globally without removing the mixin:

```ini
AUDIT_ENABLED=false
```

Individual reads still work — existing entries stay queryable.

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

- `ActivityQuery` has no `paginate` — only `AuditLog` does. Slice with `get()` and paginate in Python, or add a limit at the query layer yourself.
- Audit entries flush in the same transaction as the model save — if the transaction rolls back, the audit row rolls back too.
- `__audit_exclude__` works but isn't covered by the package's own tests.
