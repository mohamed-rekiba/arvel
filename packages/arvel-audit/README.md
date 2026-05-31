# arvel-audit

Automatic audit trail and a fluent activity log for [Arvel](https://github.com/mohamed-rekiba/arvel).

Two capabilities in one package:

- **Audit trail** — add `Auditable` to a model and every create/update/delete writes an
  `AuditEntry` (old values, new values, actor) inside the same transaction. No per-model
  observer or middleware code.
- **Activity log** — record business events ("user exported report") with a fluent
  `activity(...).log(...).by(...).on(...).save()` chain.

## Install

```bash
uv add "arvel[audit]"
arvel audit:install   # publishes the audit_entries + activity_entries migrations
arvel migrate
```

## Audit trail

```python
from arvel.database import Model
from arvel_audit import Auditable

class Invoice(Model, Auditable):
    __tablename__ = "invoices"
    __audit_redact__ = {"card_number", "cvv"}  # masked as "***" in the trail

    # ... columns ...
```

Creating, updating, or deleting an `Invoice` now records an `AuditEntry` automatically. The
actor is read from `Context.get("user_id")` when present, else stored as `None`.

Query the trail:

```python
from arvel_audit import AuditLog

history = await AuditLog(session).for_model(invoice).get()
mine = await AuditLog(session).by_actor(user.id).action("updated").get()
page = await AuditLog(session).for_model(invoice).paginate(per_page=50)
```

## Activity log

```python
from arvel_audit import activity, ActivityQuery

await (
    activity("exports", session=session)
    .log("Exported Q1 report")
    .by(user)
    .on(report)
    .with_properties({"format": "pdf", "rows": 1200})
    .save()
)

entries = await ActivityQuery(session).for_subject(report).get()
```

## Encryption

Set `AUDIT_ENCRYPT_VALUES=true` to store `old_values`/`new_values` as AES-256-GCM ciphertext
(keyed from `APP_KEY`). Reads transparently decrypt.

See `docs/site/docs/audit.md` for the full reference.
