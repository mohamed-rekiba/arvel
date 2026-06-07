# ADR-023 — `arvel-audit`

**Status**: Accepted
**Date**: 2026-06-07 (first written down here; the package itself shipped earlier as pre-alpha)
**Scope**: All architectural decisions for the `arvel-audit` package — package shape, the two logging layers, the `Auditable` mixin and observer wiring, the polymorphic identity scheme, the activity recorder, and at-rest encryption of value blobs.

## Why this is one ADR

`arvel-audit` is a small, self-contained companion package with five decisions that all touch the same machinery (model lifecycle hooks, polymorphic FKs, optional encryption). Following the WI-arvel-005 catalog rule — one ADR per shippable subsystem — every architectural decision for the package lives here in `§` sections.

---

## § 1 — Two logging layers in one package

### Context

Audit needs in a typical app split cleanly in two:

1. **Audit trail** — "what changed on this row?" Mechanical record of every create / update / delete on selected models. Old values, new values, actor.
2. **Activity log** — "what happened in the system?" Free-form business events: "user exported the Q1 report", "admin promoted user X to manager". Subject + causer + arbitrary properties.

Laravel addresses these with two separate community packages (`owen-it/laravel-auditing` for the trail, `spatie/laravel-activitylog` for the log). Each has its own model, observer, query API, and configuration surface. We considered the same split.

### Decision

Ship both layers in **one package** (`arvel-audit`), with one provider, one config class, and two storage tables (`audit_entries`, `activity_entries`). The layers share `_identity.py` (polymorphic morph helpers), exception types, and the encryption hook, but their public APIs are separate:

- Trail: `Auditable` mixin → `AuditEntry` rows. Read with `AuditLog`.
- Log: `activity()` recorder → `ActivityEntry` rows. Read with `ActivityQuery`.

### Consequences

- One install, one provider registration, one set of migrations to publish — the operational surface matches the small footprint.
- Shared identity helpers (morph map integration, model-key extraction) avoid two implementations drifting.
- `AuditConfig` carries the knobs for both layers — one configuration object to learn.
- Apps that want only the activity log still pay for the (cheap) `Auditable` registry — acceptable; the cost is a `set` and one `__init_subclass__` hook per audited model.

### Alternatives considered

- **Two packages** (`arvel-audit-trail`, `arvel-activity-log`): forced consumers to install two extras, duplicate migrations, duplicate provider wiring. The two needs co-occur enough that the split was theatre.
- **Single layer that does both**: rejected. The trail is mechanical and per-row; the log is semantic and free-form. One API for both forces awkward names (`activity().on(invoice).log("updated")` would be a worse audit trail than `Auditable`).

---

## § 2 — `Auditable` records via the model's own lifecycle events, in the same transaction

### Context

To record `AuditEntry` rows we need a hook that fires when a model is persisted. Three obvious options:

1. **SQLAlchemy `before_insert` / `before_update` / `before_delete` events** — runs at flush time, model-class scoped.
2. **A middleware around the request handler** — observes commits at the HTTP boundary.
3. **Arvent's own `on("created" | "updating" | "updated" | "deleting" | "deleted")` lifecycle hooks** — the same hook surface every Arvent feature uses.

### Decision

Use **option 3** — wire `Auditable` into Arvent's lifecycle events via `cls.on("updating", ...)`, etc. The `__init_subclass__` hook on `Auditable` registers the observers automatically the first time a subclass is defined. A class-level `_audit_wired` flag keeps it idempotent across re-imports / re-boots.

The persistence call (`session.add(entry); await session.flush()`) runs through the **same `AsyncSession` that's already active for the change** (`get_active_session()`). That guarantees the audit row is written in the same DB transaction as the change it describes — they commit and roll back together.

### Consequences

- No middleware required. The audit trail works the same in HTTP requests, queue workers, scheduled commands, and tests.
- An `Invoice.update(status="paid")` and its `AuditEntry` are atomic: a rollback after the update also rolls back the audit row. No half-truths in the trail.
- `AuditConfig().enabled = False` is checked inside the observer — toggling the flag turns off recording globally without unwiring observers (re-enabling is instant).
- Updating: capturing the "before" snapshot has to happen in `updating` (before flush clears the dirty map). We stash it on the instance in `_audit_pending_update` and consume it in `updated`. Same pattern for `deleting` / `deleted`.
- Doesn't depend on any HTTP plumbing, so it composes with workers and CLI tooling out of the box.

### Alternatives considered

- **SQLAlchemy events directly**: would couple `arvel-audit` to SQLAlchemy internals (`before_flush`, `after_flush_postexec`) instead of Arvent's stable hook surface. We'd lose Arvent-level features like `withoutEvents()` / quiet persistence (ADR-007 § 8) without re-implementing them.
- **Middleware-only**: doesn't see writes from queue workers, schedulers, seeders, fixtures, or shell sessions. Half-coverage.

---

## § 3 — Redaction and exclusion via class attributes, not column metadata

### Context

A model usually has columns that should never appear in the audit trail: passwords, tokens, card numbers, PII subject to GDPR, etc. The trail also doesn't need volatile noise (`updated_at`, computed counters). We need a way to mark columns.

Options:

1. **Per-column metadata** — `string(200, sensitive=True)` on the column declaration.
2. **Class attributes** — `__audit_redact__ = {"password"}` and `__audit_exclude__ = {"updated_at"}`.
3. **A separate decorator** — `@audit_redact("password")`.

### Decision

Class attributes:

```python
class Invoice(Model, Auditable):
    __audit_redact__ = {"card_number", "cvv"}     # written as "***" in old/new values
    __audit_exclude__ = {"updated_at", "_etag"}   # not in the entry at all
```

`__audit_redact__` masks the value with the constant `REDACTED = "***"`. `__audit_exclude__` skips the column from both `old_values` and `new_values`. Both accept `frozenset` / `set` / `tuple`.

### Consequences

- Audit policy lives next to the audit declaration — readers see the trail's surface in one block.
- Doesn't pollute the column DSL with cross-cutting concerns. Other features (search indexability, encryption) want their own column lists; pushing each into the column declaration would balloon its kwargs.
- Cheap to override per subclass. A child class that needs a different redaction set just sets its own.
- Activity recorder reads `audit_redacted_fields()` from a subject's class to drop redacted keys from `properties`, so a redacted column on the subject can't leak through the activity log either.

### Alternatives considered

- **Per-column `sensitive=True`**: mixes orthogonal concerns. A column might be sensitive *and* searchable *and* encrypted — three flags.
- **Decorator on the class**: same intent as the class attributes but with worse ergonomics for inheritance overrides.

---

## § 4 — Polymorphic identity via `_identity.py` (morph type + string-cast key)

### Context

`audit_entries` and `activity_entries` reference any model by `(model_type, model_id)` / `(subject_type, subject_id, causer_type, causer_id)`. Models in the codebase have integer PKs, UUID PKs, and (rarely) string PKs.

We need a stable scheme that:

- Round-trips any PK type through a single `VARCHAR` column.
- Honours the framework's morph map (ADR-008 § 4) — `User` not `app.models.user.User`.
- Doesn't ship a custom SQL `TypeDecorator` per package.

### Decision

`_identity.py` exposes two pure functions: `morph_type(instance)` returns the morph token (short class name by default, mapped name if registered with the framework's morph map), and `model_key(instance)` returns the primary-key value as a string. Both `Auditable._persist` and `ActivityRecorder.save` route through these helpers, never through ad-hoc casts.

The schema columns are `VARCHAR(36)` (matches Arvel's standard PK encodings — int as digits, UUID as canonical string).

### Consequences

- Audit entries point at the same morph tokens as polymorphic relationships elsewhere — the morph map (ADR-008 § 4) is one source of truth across the framework.
- One column type for any host model. No schema branch per PK kind.
- Tests can mock identity by stubbing the helpers, not by setting up a fake DB type.

### Alternatives considered

- **Fully-qualified Python paths** (`app.models.invoice.Invoice`): brittle on refactor; a class rename invalidates the trail.
- **Per-model FK column with a discriminator union type**: would require a separate audit table per PK kind (or polymorphic associations on the audit table itself). Massive overkill for a write-mostly log.

---

## § 5 — Optional AES-256-GCM encryption of `old_values` / `new_values`

### Context

The audit trail captures previous and new values verbatim. For models that contain personal or regulated data, the trail itself becomes a compliance liability — the table holds plaintext copies of every change. Three options:

1. **Always encrypt**: simple, but read-paths now require decryption for every query.
2. **Never encrypt**: simple, but consumers must redact aggressively (which discards information).
3. **Opt-in encryption** via config flag.

### Decision

Opt-in. `AUDIT_ENCRYPT_VALUES=true` switches the storage of `old_values` / `new_values` to AES-256-GCM ciphertext, keyed from `APP_KEY`. Reads decrypt transparently — the public API on `AuditEntry` continues to expose plain dicts.

### Consequences

- New deployments choose at install time: encrypted trail or plaintext. There's no "run a migration to switch" story — the tradeoff is per-deployment.
- Encryption uses the framework's existing `EncryptedType` machinery (ADR-007 § 6) — no new crypto code in this package.
- Redaction (`__audit_redact__`) still applies *before* encryption, so secrets are doubly protected: never stored in cleartext at the entry level, never encrypted at rest in their original form.
- Disabling decryption for a hostile reader (without `APP_KEY`) keeps the table audit-shaped (you can still see *which* model changed and *who* did it) but hides the values.

---

## § 6 — Activity recorder takes an explicit `AsyncSession`; audit trail uses the active session

### Context

The audit trail's `_persist` function calls `get_active_session()` because the model lifecycle hook fires inside the change's own transaction — there must already be one. The activity log is different: it's invoked from request handlers, queue jobs, and ad-hoc scripts, sometimes with a session already in flight, sometimes not.

### Decision

`activity()` requires `session=` as an explicit keyword:

```python
await activity("exports", session=db).log("...").by(user).on(report).save()
```

There's no `Activity.write(...)` shortcut that pulls an implicit session. The trail observers, by contrast, never take a `session` argument — they always use the one already running the change.

### Consequences

- The activity log is honest about its dependency on a session. No spooky action through context-locals. Easy to test (pass a fixture session) and to reason about commit boundaries.
- The trail stays ergonomic. Models don't expose a session argument to the user — they shouldn't have to.
- Two different conventions in one package. Documented; the rationale is in this ADR.

---

## Cross-references

- ADR-001 § 4 (single-`arvel` package + extras): `arvel[audit]` follows the framework's package strategy.
- ADR-007 § 6 (EncryptedType: AES-GCM): § 5 above reuses the framework crypto helper.
- ADR-007 § 8 (event suppression / quiet persistence): `Auditable` honours the suppression flag automatically.
- ADR-008 § 4 (morph map): `_identity.morph_type()` consults the same registry.
- ADR-010 (Auth): the trail's actor is read from `Context.get("user_id")`, populated by `AuthMiddleware`.
- User-facing docs: `docs/site/docs/packages/audit.md`.
