# arvel-audit

<p>
<a href="https://pypi.org/project/arvel-audit/">
    <img src="https://img.shields.io/pypi/v/arvel-audit?color=%2334D058&label=pypi" alt="PyPI">
</a>
<img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</p>

Automatic audit trail and a fluent activity log for [Arvel](https://arvel.dev).

Two logging layers in one package:

- **Audit trail** — add `Auditable` to a model and every create / update / delete writes an
  `AuditEntry` (old values, new values, actor) inside the same transaction. No per-model observer or
  middleware code.
- **Activity log** — record business events ("user exported report") with the fluent `activity()`
  API, modeled after Spatie's Laravel ActivityLog.

> **Status**: Pre-alpha.

---

**Documentation**: <a href="https://arvel.dev/packages/audit" target="_blank">https://arvel.dev/packages/audit</a>

---

## Install

```bash
uv add "arvel[audit]"
# or: pip install arvel-audit
```

Register the provider in `bootstrap/providers.py`:

```python
from arvel_audit import AuditServiceProvider

providers = [
    # ...other providers...
    AuditServiceProvider,
]
```

Publish the migrations (`audit_entries`, `activity_entries`) and run them:

```bash
arvel vendor:publish --tag=arvel-audit   # or: arvel audit:install
arvel migrate
```

The provider binds `AuditConfig` and wires the `Auditable` observers on boot.

## Audit trail

```python
from arvel.database import Model, id_, string
from arvel_audit import Auditable


class Invoice(Model, Auditable):
    __tablename__ = "invoices"
    __audit_redact__ = {"card_number", "cvv"}   # masked as "***" in the trail

    id: int = id_()
    status: str = string(20, default="new")
```

Creating, updating, or deleting an `Invoice` now records an `AuditEntry` automatically. The actor is
read from `Context.get("user_id")` when present, otherwise stored as `None`.

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

Set `AUDIT_ENCRYPT_VALUES=true` to store `old_values` / `new_values` as AES-256-GCM ciphertext (keyed
from `APP_KEY`). Reads decrypt transparently.

See the [full reference](https://arvel.dev/packages/audit) for column control and query options.

## License

MIT — see [LICENSE](../../LICENSE).
