# Epic 004: Audit Trail & Activity Log (`arvel-audit`)

## Summary

A new companion package (`arvel-audit`) combining two capabilities: an automatic audit trail that
records model create/update/delete events with old and new values (Spatie Laravel Auditing parity),
and a fluent activity log recorder for business-level events (Spatie Laravel ActivityLog parity).
The key improvement over `arvel_old`: `Auditable` auto-records via an observer — no manual
`AuditLog.record()` calls required.

---

## Stories

### Story 1: Automatic model audit trail via `Auditable` mixin

**As a** framework user,
**I want** to add an `Auditable` mixin to my model and have create/update/delete events recorded automatically,
**so that** I get a full change history without writing observer or middleware code for each model.

**Acceptance Criteria**:
- [ ] Given a model declares `class Invoice(Model, Auditable)`, when a new `Invoice` is created, then an `AuditEntry` with `action="created"`, `new_values={all columns}`, and `old_values={}` is inserted
- [ ] Given an `Invoice` field changes, when the record is saved, then an `AuditEntry` with `action="updated"`, `old_values={changed fields before}`, and `new_values={changed fields after}` is inserted
- [ ] Given an `Invoice` is deleted, when the record is removed, then an `AuditEntry` with `action="deleted"`, `old_values={last known values}`, and `new_values={}` is inserted
- [ ] Given `class Invoice(Model, Auditable): __audit_redact__ = {"card_number", "cvv"}`, when an `AuditEntry` is written, then `card_number` and `cvv` appear as `"***"` in both `old_values` and `new_values`
- [ ] Given `AuditServiceProvider` is registered, when `boot()` runs, then `AuditObserver` is registered for all models implementing `Auditable` via `ObserverRegistry`
- [ ] Given no actor is in context, when an audit entry is recorded, then `actor_id` is `None` (not an error)
- [ ] Given `Context.get("user_id")` returns a value, when an audit entry is recorded, then `actor_id` is set to that value automatically

**Security Requirements**:
- [ ] Fields in `__audit_redact__` must be redacted before the entry reaches the database — not post-hoc on read
- [ ] `old_values` and `new_values` must be stored as encrypted JSON if `AUDIT_ENCRYPT_VALUES=true` is set (uses `EncryptedType`)
- [ ] `AuditEntry` table must have a non-nullable `model_type` and `model_id` to prevent orphaned records

**Documentation Requirements**:
- [ ] Add `docs/site/docs/audit.md` covering `Auditable` mixin, `__audit_redact__`, and querying audit entries

**Requirement Refs**: Brainstorm design § Phase 2C
**Priority**: Must
**Complexity**: Medium
**Status**: Done

---

### Story 2: Audit entry query API

**As an** application operator,
**I want** to query the audit trail by model instance, time range, actor, and action type,
**so that** I can answer "who changed what and when" for compliance investigations and debugging.

**Acceptance Criteria**:
- [ ] Given `AuditLog(session).for_model(invoice)`, when called, then all `AuditEntry` records for that `invoice` instance are returned in chronological order
- [ ] Given `.by_actor(user_id)`, when chained, then only entries where `actor_id == user_id` are returned
- [ ] Given `.action("updated")`, when chained, then only `updated` entries are returned
- [ ] Given `.since(datetime)` and `.until(datetime)`, when chained, then results are filtered to the time window
- [ ] Given a model has hundreds of audit entries, when `.paginate(per_page=50)` is called, then results are paginated using the ORM paginator
- [ ] Given an invalid action string is passed to `.action()`, when the query runs, then an `InvalidAuditAction` exception is raised with valid options listed

**Security Requirements**:
- [ ] Audit query results must never be exposed to end users directly — access control is the application's responsibility (not enforced at the `AuditLog` layer)

**Documentation Requirements**:
- [ ] Add query API reference section to `docs/site/docs/audit.md`

**Requirement Refs**: Brainstorm design § Phase 2C
**Priority**: Must
**Complexity**: Small
**Status**: Done

---

### Story 3: Fluent activity recorder for business events

**As a** framework user,
**I want** a fluent `ActivityRecorder` API for logging business-level events (e.g., "user exported report"),
**so that** I can maintain an activity log separate from the technical audit trail without writing raw SQL.

**Acceptance Criteria**:
- [ ] Given `activity("exports", session=session).log("Exported Q1 report").by(user).on(report).save()`, when called, then an `ActivityEntry` is inserted with `log_name="exports"`, `description="Exported Q1 report"`, `causer_type="User"`, `causer_id=user.id`, `subject_type="Report"`, `subject_id=report.id`
- [ ] Given `.with_properties({"format": "pdf", "rows": 1200})`, when the entry is saved, then `properties` is stored as JSON
- [ ] Given `ActivityQuery(session).for_subject(report)`, when called, then all activity entries where `subject_type="Report"` and `subject_id=report.id` are returned
- [ ] Given `ActivityQuery(session).by_causer(user)`, when called, then all entries caused by that user are returned
- [ ] Given neither `.by()` nor `.on()` is called, when `.save()` runs, then `causer_id` and `subject_id` are `None` (not an error)
- [ ] Given `.log()` is never called before `.save()`, when `.save()` runs, then `MissingActivityDescription` is raised

**Security Requirements**:
- [ ] `properties` JSON must not include fields from `__audit_redact__` of the subject model if the subject is an `Auditable` — cross-check at `save()` time

**Documentation Requirements**:
- [ ] Add activity recorder section to `docs/site/docs/audit.md`

**Requirement Refs**: Brainstorm design § Phase 2C
**Priority**: Should
**Complexity**: Small
**Status**: Done

---

### Story 4: `arvel audit:install` command and migrations

**As a** framework user,
**I want** an `arvel audit:install` command that publishes the audit and activity migrations,
**so that** I can add the audit package to an existing project without manually writing migration files.

**Acceptance Criteria**:
- [ ] Given `arvel audit:install` is run, when the command completes, then two migration files are published to `db/migrations/`: one for `audit_entries` and one for `activity_entries`
- [ ] Given the `audit_entries` migration runs, when the table is created, then it has: `id`, `actor_id`, `action` (enum: created/updated/deleted), `model_type`, `model_id`, `old_values` (JSON), `new_values` (JSON), `created_at`; plus an index on `(model_type, model_id)`
- [ ] Given the `activity_entries` migration runs, when the table is created, then it has: `id`, `log_name`, `description`, `subject_type`, `subject_id`, `causer_type`, `causer_id`, `properties` (JSON), `created_at`; plus an index on `(subject_type, subject_id)` and `(causer_type, causer_id)`
- [ ] Given `arvel audit:install` is run when migrations already exist, when the command detects duplicates, then it exits with a clear message and does not overwrite

**Security Requirements**:
- [ ] Indexes on `(model_type, model_id)` and `(causer_type, causer_id)` must exist to prevent full-table scans on audit queries in production databases

**Documentation Requirements**:
- [ ] Add `arvel audit:install` reference to `docs/site/docs/audit.md`

**Requirement Refs**: Brainstorm design § Phase 2C
**Priority**: Must
**Complexity**: Small
**Status**: Done

---

## Dependencies

- Depends on Epic 001 Story 1 (`context/` module) — `actor_id` is read from `Context.get("user_id")` automatically
- Requires `arvel` core `data/` module (`ObserverRegistry`, `ArvelModel`, `EncryptedType`) for observer registration and optional encryption
- `AuditServiceProvider` must be registered after `DatabaseServiceProvider` (DB must be up to insert entries)

## Notes

- The two audit systems from `arvel_old` are unified: `arvel.audit` (DB trail) and `arvel.auth.audit` (security event logger) remain distinct — `arvel-audit` is the DB trail only; auth security events continue via `Log.audit(...)` channel in core
- `Auditable` auto-records via `AuditObserver` — manual `AuditLog.record()` is still available for edge cases (e.g., bulk operations that bypass ORM events)
- Soft-deleted records: `deleted` audit event fires on soft-delete (not only hard delete) when the model implements `SoftDeletes`
