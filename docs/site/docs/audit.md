# Audit & Activity Log

`arvel-audit` gives you two complementary histories:

- An **audit trail** — add the `Auditable` mixin to a model and every create, update, and
  delete records an `AuditEntry` (old values, new values, the acting user) inside the same
  transaction as the change. No per-model observer or middleware code.
- An **activity log** — record business-level events ("user exported a report") through a
  fluent `activity(...)` recorder, separate from the technical audit trail.

`arvel-audit` is a separate workspace package. Install it through the `audit` extra:

```bash
uv add "arvel[audit]"
```

Then publish and run the migrations:

```bash
arvel audit:install
arvel migrate
```

## The `Auditable` mixin

Add `Auditable` to a model. Lifecycle hooks wire automatically at class definition — there
is nothing to register per model.

```python
from arvel.database import Model, id_, integer, string
from arvel_audit import Auditable


class Invoice(Model, Auditable):
    __tablename__ = "invoices"

    id: int = id_()
    number: str = string(255)
    amount: int = integer(default=0)
```

What gets recorded:

| Event | `action` | `old_values` | `new_values` |
|---|---|---|---|
| Create | `created` | `{}` | every column |
| Update | `updated` | changed columns, before | changed columns, after |
| Delete | `deleted` | last known column values | `{}` |

Saving a model with no dirty columns records nothing. Soft deletes record a `deleted` entry
just like hard deletes.

### Redacting sensitive columns

List columns in `__audit_redact__` and they are masked as `"***"` **before** the entry is
written — the plaintext never reaches the database, not even transiently.

```python
class CardPayment(Model, Auditable):
    __tablename__ = "card_payments"
    __audit_redact__ = {"card_number", "cvv"}
    # ...
```

Use `__audit_exclude__` to drop columns from the trail entirely (for example, noisy
timestamps you don't care to track).

### The acting user

The actor is read from the request-scoped context: whatever `Context.get("user_id")` returns
is stored as `actor_id`. With no context bound (CLI, workers), `actor_id` is `None` — never an
error.

```python
from arvel.context import Context

Context.add("user_id", current_user.id)  # set once per request, e.g. in middleware
```

## Querying the audit trail

`AuditLog` is a thin, chainable query over `audit_entries`. Results come back in chronological
order (oldest first).

```python
from arvel_audit import AuditLog

# Full history for one record
history = await AuditLog(session).for_model(invoice).get()

# Everything a given user changed, updates only
changes = await AuditLog(session).by_actor(user.id).action("updated").get()

# Within a time window
from datetime import datetime, UTC, timedelta
recent = await (
    AuditLog(session)
    .for_model(invoice)
    .since(datetime.now(UTC) - timedelta(days=7))
    .get()
)

# Paginated with the ORM paginator
page = await AuditLog(session).for_model(invoice).paginate(per_page=50, page=1)
```

`action()` only accepts `created`, `updated`, or `deleted`. Anything else raises
`InvalidAuditAction` with the valid options listed.

!!! warning "Access control is your job"
    `AuditLog` returns unredacted history (apart from columns you redacted at write time).
    Never expose its results to end users directly — gate them behind your own authorization.

## The activity log

Record business events with a fluent chain. The recorder is bound to a session and persists on
`save()`.

```python
from arvel_audit import activity

await (
    activity("exports", session=session)
    .log("Exported Q1 report")
    .by(current_user)       # the causer
    .on(report)             # the subject
    .with_properties({"format": "pdf", "rows": 1200})
    .save()
)
```

- `.by()` and `.on()` are optional — omit them and `causer_id` / `subject_id` are `None`.
- Calling `.save()` without `.log(...)` first raises `MissingActivityDescription`.
- If the subject is `Auditable`, any property whose key is in the subject's `__audit_redact__`
  is stripped before the entry is written.

Read activity back by subject or causer:

```python
from arvel_audit import ActivityQuery

for_report = await ActivityQuery(session).for_subject(report).get()
by_user = await ActivityQuery(session).by_causer(current_user).get()
```

## Encryption at rest

Set `AUDIT_ENCRYPT_VALUES=true` and the `old_values` / `new_values` blobs are stored as
AES-256-GCM ciphertext, keyed from `APP_KEY`. Reads decrypt transparently, so the query API is
unchanged. Leave it unset (the default) to store native JSON.

```dotenv
AUDIT_ENCRYPT_VALUES=true
```

## `arvel audit:install`

Publishes two migrations into `database/migrations/`:

- `create_audit_entries_table` — `audit_entries` with an index on `(model_type, model_id)`
- `create_activity_entries_table` — `activity_entries` with indexes on
  `(subject_type, subject_id)` and `(causer_type, causer_id)`

```bash
arvel audit:install          # skips files that already exist
arvel audit:install --force  # overwrite existing files
```

The composite indexes keep per-record and per-causer lookups off full-table scans on
production-sized tables.
