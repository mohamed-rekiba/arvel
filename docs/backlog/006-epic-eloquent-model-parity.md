# Epic: Eloquent Model Parity (Attributes & Lifecycle)

## Summary

Bring Arvent's model layer to parity with Laravel Eloquent's attribute pipeline and model
lifecycle. Covers casts, accessors/mutators, mass assignment, dirty tracking, serialization,
events/observers, scopes, soft deletes, timestamps, pruning, factories, and an Eloquent-style
model collection. Findings come from the parity review against
`repos/lv-app/vendor/laravel/framework/src/Illuminate/Database/Eloquent`.

Arvel already has primitive casts, `@accessor`/`@mutator`, dirty-tracking basics, async observers
with cancellable before-hooks, named global scopes, `@scope` local scopes, soft deletes,
timestamps, `Prunable`, and a factory core. The stories below close the extensibility and
ergonomics gaps.

## Stories

### Story 1: Attribute-level custom cast protocol — DONE (WI-arvel-005, ADR-127)
**As a** developer, **I want** a `CastsAttributes`-style protocol usable from `__casts__` (e.g. `__casts__ = {"meta": AsCollection}`), **so that** I can define virtual, computed, or multi-column casts without changing the SQLAlchemy column type.

**Acceptance Criteria**:
- [x] Given a cast class with `get(model, key, value)` / `set(model, key, value)`, when registered in `__casts__`, then reads and writes route through it.
- [x] Given a parameterized cast spec (`"decimal:2"`), then the parameter is parsed and passed to the cast. (Named-registry form `"AsCollection:CustomCollection"` deferred — pass the cast class/instance directly instead; see ADR-127-03.)
- [x] Given a custom cast, when the attribute is serialized via `to_dict`, then the cast's serialized form is used.

**Documentation Requirements**:
- [ ] Document the cast protocol with a worked example.

**Priority**: Must
**Complexity**: Large

### Story 2: `hashed` cast + `force_fill` + unguard
**As a** developer handling passwords and seeds, **I want** a `"hashed"` cast, `force_fill()`, and `Model.unguard()/unguarded()`, **so that** password hashing is declarative and admin/seed flows can bypass mass-assignment safely.

**Acceptance Criteria**:
- [ ] Given `"password": "hashed"`, when set, then the value is hashed on write and passed through if already hashed.
- [ ] Given `force_fill(**attrs)`, then all attributes are assigned regardless of fillable/guarded.
- [ ] Given `with Model.unguarded():`, then mass-assignment guards are suspended for the block and restored after.

**Security Requirements**:
- [ ] `force_fill` and `unguarded` are explicit, never the default path for request data.
- [ ] Hashed values use the project's `Hash` facade (bcrypt/argon2), never a weak hash.

**Priority**: Must
**Complexity**: Medium

### Story 3: Declarative `encrypted` casts — DONE (WI-arvel-018, ADR-137)
**As a** developer storing PII, **I want** `"encrypted"`, `"encrypted:array"`, `"encrypted:json"` cast specs in `__casts__`, **so that** encryption is declarative and rotates with the app encrypter, not only via column-level `EncryptedType`.

**Acceptance Criteria**:
- [x] Given `"secret": "encrypted:array"`, when read/written, then the value is JSON-encoded then encrypted (and reversed on read). (Also `encrypted`, `encrypted:json`, `encrypted:object`, `encrypted:collection`.)
- [x] Given a key rotation, then previously stored values still decrypt. (Crypt caches per `APP_KEY`; a changed key rebuilds the encrypter. Multi-key co-existence is deferred to a future rotation story.)
- [x] Given `to_dict()`, then the decrypted value is exposed (Eloquent `toArray` parity).

**Security Requirements**:
- [x] Encryption uses the app encrypter; keys come from `APP_KEY` (env/secret manager), never code (A04). 32-byte AES-256-GCM key HKDF-derived from `APP_KEY`; random IV per write.

**Priority**: Should
**Complexity**: Medium

### Story 4: Cast-aware dirty tracking — DONE (WI-arvel-006, ADR-128)
**As a** developer relying on `is_dirty`/`get_original`, **I want** cast-aware comparison (`original_is_equivalent`) and `get_raw_original`, **so that** `"1"` vs `1`, decimal strings, JSON, and encrypted fields don't produce false dirty results.

**Acceptance Criteria**:
- [x] Given a boolean cast over an integer column, when the value is unchanged semantically, then `is_dirty()` returns `False`.
- [x] Given `get_raw_original(key)`, then it returns the pre-cast committed value.
- [x] Given `get_original(key)`, then it returns the cast/accessor-transformed value (matching Laravel).

**Priority**: Should
**Complexity**: Medium

### Story 5: Unified accessor/mutator (`Attribute`-style) with caching — DONE (WI-arvel-019, ADR-138)
**As a** developer, **I want** a single descriptor defining symmetric `get`/`set` for one virtual attribute (e.g. `name` backed by `first_name`/`last_name`) with optional value caching, **so that** computed attributes don't need split `@accessor`/`@mutator` on different names.

**Acceptance Criteria**:
- [x] Given an `Attribute`-style descriptor with `get` and `set`, then both reads and writes route through it under one attribute name.
- [x] Given caching enabled (`.should_cache()`), then the computed value is cached per instance and invalidated on a `set` through the attribute.

**Priority**: Should
**Complexity**: Medium

### Story 6: Enum and extended built-in casts — DONE (WI-arvel-017, ADR-136)
**As a** developer, **I want** `enum` casts in `__casts__` plus `decimal:n`, `datetime:FORMAT`, `object`, and `collection` casts, **so that** declarative casting covers Laravel's common built-ins.

**Acceptance Criteria**:
- [x] Given `"status": StatusEnum`, when read, then the value is the enum member; on write, the backing value is stored.
- [x] Given `"price": "decimal:2"`, then reads/writes quantize to a `Decimal` with the given scale. (Shipped in WI-arvel-005.)
- [x] Given `"tags": "collection"`, then reads return an Arvel `Collection`.
- [x] Given `"meta": "object"`, then reads return an attribute-accessible namespace; serialize emits a plain dict.
- [x] Given `"scheduled_at": "datetime:%Y-%m-%d %H:%M"`, then serialize emits `strftime(FORMAT)`.

**Priority**: Should
**Complexity**: Medium

### Story 7: `without_events()` + quiet persistence
**As a** developer running seeders, backfills, and recursive updates, **I want** a re-entrant `Model.without_events()` context and `save_quietly`/`delete_quietly`/`update_quietly`/`force_delete_quietly`/`restore_quietly`, **so that** I can persist without firing observers.

**Acceptance Criteria**:
- [ ] Given `async with Model.without_events():`, when models are saved inside, then no lifecycle observers fire, and firing resumes after the block (re-entrant safe).
- [ ] Given `save_quietly()`, then the row persists with no events.
- [ ] Existing observer behavior outside these contexts is unchanged.

**Priority**: Must
**Complexity**: Medium

### Story 8: Eloquent-style `ModelCollection` — DONE (WI-arvel-037, ADR-156)
**As a** developer working with result sets, **I want** `all()` to return a `ModelCollection` with `load`/`load_missing`, `model_keys`, PK-aware `contains`/`find`/`only`/`except`/`diff`/`intersect`, `to_query`, `fresh`, and `make_hidden`/`make_visible`, **so that** collection operations match Eloquent.

**Acceptance Criteria**:
- [x] Given a `ModelCollection`, when `load("rel")` is called, then the relation is batch-loaded for all members in a fixed number of queries (async/pivot/morph via the epic-007 path; SA relations via one `select(... pk IN keys)` + `selectinload`). `load_missing` only loads relations not yet populated.
- [x] Given `model_keys()`, then it returns the list of primary keys in order.
- [x] Given `find(pk)` / `contains(pk)` / `only`/`except_`/`diff`/`intersect`, then lookup/filtering is by primary key (`get_key`), not object identity. Plus `to_query` (WHERE pk IN keys), `fresh` (re-fetch preserving order), and `make_hidden`/`make_visible` across all members.

**Priority**: Should
**Complexity**: Large

### Story 9: Static event registration + custom event objects — DONE (WI-arvel-020, ADR-139)
**As a** developer, **I want** `Model.on("created", cb)` callable registration, `__dispatches_events__` mapping lifecycle names to event classes, and `#[ObservedBy]`-style auto-registration via a class attribute, **so that** lifecycle wiring doesn't require a full observer class for every hook.

**Acceptance Criteria**:
- [x] Given `Model.on("created", cb)`, then `cb` runs after create alongside any observers. Cancellable hooks (`creating` etc.) honor a `False` return; async callbacks are awaited.
- [x] Given `__dispatches_events__ = {"created": UserCreated}`, then the mapped event object (a `ModelEvent` carrying the instance) is dispatched on the app event bus. No dispatcher bound → silently skipped (pure-DB tests stay green).
- [x] Given `__observed_by__ = [AuditObserver]`, then the observer is registered at class-definition time via `__init_subclass__`.

**Priority**: Should
**Complexity**: Medium

### Story 10: Soft-delete upsert and bulk restore — DONE (WI-arvel-022, ADR-141)
**As a** developer running sync/import flows, **I want** `restore_or_create`/`create_or_restore`, a bulk `QueryBuilder.restore()`, an instance `trashed()` helper, and `force_destroy(ids)`, **so that** the restore-if-trashed-else-create pattern and bulk restores are first-class.

**Acceptance Criteria**:
- [x] Given a trashed row, when `restore_or_create(attrs)` runs, then the row is restored rather than duplicated (searches `with_trashed`).
- [x] Given `query().only_trashed().restore()`, then matching rows have `deleted_at` cleared in one UPDATE. Bulk writes bypass per-row events (Eloquent parity); instance `restore()` still fires `restored`.
- [x] Given an instance, `trashed()` returns whether `deleted_at` is set. Plus `create_or_restore` alias and `force_destroy(*ids)` (hard delete by PK, trashed included).

**Priority**: Should
**Complexity**: Medium

### Story 11: Distinct soft/hard-delete and replicate events — DONE (WI-arvel-023, ADR-142)
**As a** developer observing models, **I want** distinct `trashed`, `force_deleting`/`force_deleted`, and `replicating` events (instance and bulk), **so that** listeners can tell soft deletes from hard deletes and react to clones.

**Acceptance Criteria**:
- [x] Given an instance soft delete, then `trashed` fires (alongside `deleted`). Bulk QB deletes stay event-free — set-based statements with no loaded rows (ADR-142-04, Eloquent parity).
- [x] Given `force_delete()`, then `force_deleting`/`force_deleted` fire and `trashed` does not (`deleted` still fires for both delete kinds). `force_deleting` is cancellable.
- [x] Given `replicate()`, then `replicating` fires on the clone before it is returned.

**Priority**: Could
**Complexity**: Medium

### Story 12: Timestamp controls — DONE (WI-arvel-021, ADR-140)
**As a** developer, **I want** a `__timestamps__` toggle, `CREATED_AT`/`UPDATED_AT` column-name constants, `touch(attribute)` for arbitrary columns, `touch_quietly`, and a `without_timestamps` context, **so that** imports/backfills and custom timestamp columns are supported.

**Acceptance Criteria**:
- [x] Given `__timestamps__ = False`, then create/update don't auto-fill timestamps (no hooks attached).
- [x] Given `CREATED_AT = "inserted_at"` / `UPDATED_AT = "changed_at"`, then the mapper fills the custom columns.
- [x] Given `async with Model.without_timestamps():`, then writes inside skip timestamp auto-fill (task-local).
- [x] `touch(attribute=None)` sets the column to now and saves (fires events); `touch_quietly` suppresses events.

**Priority**: Could
**Complexity**: Medium

### Story 13: Factory enhancements — DONE (WI-arvel-024, ADR-143)
**As a** test author, **I want** factory `has_attached` (pivot), a `trashed` state, Faker wired into callbacks, `create_quietly`, and per-factory connection selection, **so that** factories cover M2M, soft-deleted rows, and realistic data.

**Acceptance Criteria**:
- [x] Given `has_attached("roles", RoleFactory(), pivot={...})`, then created models get pivot rows with the given attributes.
- [x] Given `trashed()`, then the created row has `deleted_at` set (raises without `SoftDeletes`).
- [x] Given `after_creating(fn)` / `after_making(fn)`, then `fn` receives a shared Faker instance.
- [x] Plus `create_quietly()` (mutes events) and `connection(name)` (routes persistence through a named DB connection).

**Priority**: Should
**Complexity**: Medium

### Story 14: Attribute API polish bundle — DONE (WI-arvel-025, ADR-144)
**As a** developer, **I want** the remaining attribute helpers — instance `append()`/`set_appends`, `make_hidden_if`/`make_visible_if`, `only()`/`except_()`, public `get_key()`/`get_key_name()`, `qualify_column()`, `is_same()`/`is_not()`, `discard_changes()`, and `HasUuids`/`HasUlids` traits with `new_unique_id()` — **so that** the model surface matches Eloquent's helpers.

**Acceptance Criteria**:
- [x] Each listed helper exists with Laravel-equivalent semantics and a unit test.
- [x] `HasUuids`/`HasUlids` traits generate keys on insert (`before_insert` hook fills an empty string PK from `new_unique_id()`). Route-binding not-found resolution is already handled by the existing `find`/`ModelNotFoundError` path for any PK type.

**Priority**: Could
**Complexity**: Medium

## Dependencies

- Story 8 (`ModelCollection.load`) depends on epic 007's batched eager-load engine for pivot/morph relations.
- Story 7 (`without_events`) is used by Story 13 (factory `create_quietly`) and epic 007 relation factories.

## Notes

- Laravel references: `Eloquent/Model.php`, `Concerns/HasAttributes.php`, `GuardsAttributes.php`,
  `HidesAttributes.php`, `HasEvents.php`, `HasGlobalScopes.php`, `HasTimestamps.php`, `SoftDeletes.php`,
  `Prunable.php`, `Eloquent/Collection.php`, `Eloquent/Factories/Factory.php`, `Casts/*`.
- Arvel keeps Pydantic-based serialization (`to_pydantic`, `model_serialize`) as an addition, not a
  replacement — align cast serialization with it.
