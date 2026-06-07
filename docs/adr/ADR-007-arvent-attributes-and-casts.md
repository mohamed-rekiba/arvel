# ADR-007 — Arvent — Attributes, Casts & Events

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-17; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Unified attribute descriptor, cast protocol, cast-aware dirty tracking, enum casts, declarative encrypted casts, AES-GCM type, hashed cast and mass-assignment bypass, event suppression / quiet persistence, static event registration, timestamp controls, distinct delete event replay, factory enhancements.

## Why this is one ADR

Casts and events sit on the same descriptor surface — one set of rules govern reading, writing, comparing, and emitting events for any model attribute. The twelve ADRs build that surface in stages.

---

## § 1 — Unified `Attribute` descriptor

**Originally**: ADR-051

Status: Accepted (delivered WI-arvel-019)

Eloquent-parity increment (backlog `006`, story S5). Adds a single descriptor for symmetric
get/set under one attribute name. No schema or route changes.

### ADR-007 § 1-01: A Python data descriptor, not a decorated method

Status: Accepted

Laravel declares `protected function name(): Attribute` returning `Attribute::make(get:, set:)`.
The idiomatic Python equivalent is a **data descriptor** assigned to a class attribute:

```python
full_name = Attribute.make(
    get=lambda m: f"{m.first_name} {m.last_name}",
    set=lambda m, v: dict(zip(("first_name", "last_name"), v.split(" ", 1))),
)
```

`Attribute` defines `__get__`/`__set__`/`__set_name__`. Because `Model.__getattribute__` and
`__setattr__` both delegate to `super()` (i.e. `object`), the descriptor protocol fires
normally — reads call `get(model)`, writes call `set(model, value)`. No metaclass collection is
needed (unlike `@accessor`/`@mutator`, which are scanned in `__init_subclass__`).

It carries no annotation, so SQLAlchemy's `MappedAsDataclass` ignores it (not a field, not a
mapped column) — same as the `property` produced by `@accessor`.

### ADR-007 § 1-02: `set` returns a column→value mapping

Status: Accepted

A virtual attribute has no column of its own, so a scalar write has nowhere unambiguous to land.
`set` therefore returns a `Mapping[str, Any]` of real column names to values; each is assigned
through the normal `setattr` path (so casts and mutators still run). A non-mapping return raises
`TypeError` at write time. `get`-only attributes are read-only (write raises); `set`-only
attributes are write-only (read raises). For the single-column transform case, the existing
`@mutator` already suffices — `Attribute` targets the multi-column / unified-name case.

### ADR-007 § 1-03: Opt-in per-instance caching

Status: Accepted

`.should_cache()` flips a flag. The computed value is memoized in a per-instance dict
(`instance.__dict__["_arvel_attr_cache"]`, set via `object.__setattr__` to skip the cast path)
keyed by attribute name. Writing through the attribute invalidates its own cache entry. Caching
does **not** track column dependencies — mutating a backing column directly leaves a cached value
sticky (same limitation as Laravel's `shouldCache()`); use it only when that's acceptable. The
cache key is excluded from the `model_serialize` `__dict__` fallback.

---

### Merged: Attribute API polish bundle (was ADR-007 § 1)

Status: Accepted (delivered WI-arvel-025)

Eloquent-parity increment (backlog `006`, story S14) — the last of Epic 006. Fills in the remaining
model helper surface. No schema change.

### ADR-007 § 1-01: Per-instance appends

Status: Accepted

`append(*names)` adds accessor names to one instance's serialized output; `set_appends(list)`
replaces the per-instance list. Stored in a `_instance_appends` ClassVar slot (set via
`object.__setattr__`, like `_instance_hidden`) so it stays out of dataclass/ORM field processing.
`to_dict()` merges class-level `__appends__` with the per-instance list via `_collect_appends()`
(extracted to keep `to_dict` under the complexity gate).

### ADR-007 § 1-02: Conditional visibility

Status: Accepted

`make_hidden_if(condition, *fields)` / `make_visible_if(...)` apply the existing
`make_hidden`/`make_visible` only when `condition` holds. `condition` is a bool or a
`self`-predicate (`Callable[[model], bool]`), matching Laravel's bool-or-Closure form. Both return
`self` for chaining.

### ADR-007 § 1-03: `only` / `except_`

Status: Accepted

Subset helpers over `to_dict()`: `only(*keys)` keeps just those keys (missing ones skipped);
`except_(*keys)` drops them. `except_` is spelled with a trailing underscore — `except` is a Python
keyword.

### ADR-007 § 1-04: Key + column helpers

Status: Accepted

`get_key_name()` (classmethod) returns the single PK column name and raises on composite keys;
`get_key()` returns the PK value (a tuple for composite keys). `qualify_column(col)` prefixes the
table name (`"users.email"`), resolved from the mapper's local table. `is_same(other)` is true for
the same model type with the same non-null key; `is_not` is its inverse — Laravel's `is()`/`isNot()`.

### ADR-007 § 1-05: `discard_changes`

Status: Accepted

Reverts pending (dirty) column attributes back to their committed originals via SQLAlchemy's
`committed_state`, leaving the instance clean. Unflushed values with no committed original are left
as-is (nothing to revert to).

### ADR-007 § 1-06: `HasUuids` / `HasUlids` traits

Status: Accepted

Plain mixins (not `MappedAsDataclass` — they add no columns) that auto-fill an empty single-column
string PK on insert via a shared `before_insert` hook. The hook calls `type(target).new_unique_id()`
so each trait supplies its own generator: `HasUuids` → `uuid4`; `HasUlids` → a 26-char Crockford
base32 ULID (48-bit ms time + 80-bit `os.urandom`, sortable by the 10-char time prefix; randomness
within a single millisecond isn't monotonic, which is fine for keys). The model declares the PK as a
string column with `init=False, default=None` so it stays empty until the hook runs. `new_unique_id`
is a classmethod, overridable. A `_UniqueIdProvider` Protocol keeps the hook type-safe without
`Any`-widening.

---

## § 2 — Attribute-level Custom Cast Protocol

**Originally**: ADR-052

Status: Accepted

Eloquent-parity increment (backlog `006`, Sprint B: story S1). No HTTP or schema
surface — recorded as an ADR.

### ADR-007 § 2-01: `CastsAttributes` ABC with get / set / serialize

Status: Accepted

`__casts__` previously took only built-in type names (`"boolean"`, `"int"`, …). To
support virtual/computed/multi-column casts without changing the SQLAlchemy column
type, `__casts__` values now also accept a `CastsAttributes` subclass or instance:

```python
class AsUpper(CastsAttributes[str]):
    def get(self, model, key, value): return value.upper()
    def set(self, model, key, value): return value.lower()

class Doc(Model):
    __casts__ = {"code": AsUpper}   # class or AsUpper() instance
```

`get`/`set` are abstract; `serialize` defaults to returning the get value, so simple
casts don't have to implement it. `to_dict` calls `serialize` for custom-cast fields,
matching Laravel's `CastsAttributes` + `SerializesCastableAttributes`.

### ADR-007 § 2-02: Resolve casts once at class definition, not per access

Status: Accepted

`__getattribute__` runs on **every** attribute read, so parsing cast specs or
instantiating cast classes there would tax the hot path. Instead `__init_subclass__`
resolves each `__casts__` entry once into a `_ResolvedCast(read, write, serialize)`
triple cached on `cls.__arvel_cast_resolvers__`. The read/write paths then do a single
dict lookup and at most one call. Each callable has the uniform
`(model, key, value) -> value` shape; built-in coercers are adapted to ignore
`model`/`key`. This also lets validation happen at definition time (bad spec → raise on
class creation, as before).

### ADR-007 § 2-03: Parameterized string specs; `decimal:N` first

Status: Accepted

String specs may carry a colon-delimited parameter (`"decimal:2"`). The resolver splits
on the first colon and dispatches; `decimal:N` quantizes to `Decimal` at scale `N`
(`ROUND_HALF_UP`). The registry-backed named form (`"AsCollection:CustomCollection"`)
is intentionally **not** added — passing the cast class/instance directly covers the
real need without a global name registry (avoids the indirection and a mutable global).
Built-in `_READ_SKIP_CASTS` / `_WRITE_SKIP_CASTS` semantics (e.g. `hashed` write-only,
JSON read-only) are preserved by the resolver.

---

## § 3 — Cast-aware Dirty Tracking

**Originally**: ADR-053

Status: Accepted

Eloquent-parity increment (backlog `006`, Sprint B: story S4). No HTTP or schema
surface — recorded as an ADR.

### ADR-007 § 3-01: Compare original vs current at the *cast* level

Status: Accepted

`is_dirty` / `get_dirty` previously trusted SQLAlchemy's raw attribute history. That's
right for plain columns but produces false positives for custom casts: a JSON cast can
re-serialize `{"a": 1, "b": 2}` to a different string than the stored one (key order,
spacing), so the raw strings differ even though the value didn't. (Built-in scalar casts
like boolean-over-int rarely trip this, because SQLAlchemy keeps the post-cast value in
`committed_state` and `1 == True` in Python.)

`original_is_equivalent(key)` mirrors Eloquent's method: if the raw values differ, fall
back to comparing the **read-cast** values. Equal cast values ⇒ not dirty. `is_dirty` and
`get_dirty` filter SQLAlchemy-changed keys through it, so `"1"` vs `1`, decimal strings,
and re-serialized JSON read clean while genuine changes still read dirty.

### ADR-007 § 3-02: `get_original` casts, `get_raw_original` doesn't

Status: Accepted

Split the original-value accessors to match Laravel:

- `get_raw_original(key=None)` returns the pre-cast committed value (what the old
  `get_original` returned).
- `get_original(key=None)` applies the read cast, so it returns the same shape callers see
  from a live attribute read.

### ADR-007 § 3-03: Guard the `NO_VALUE` sentinel

Status: Accepted

A pending (added, not-yet-flushed) instance carries SQLAlchemy's `NO_VALUE` sentinel in
`committed_state` for attributes with no committed original — which is exactly the state
`create()` snapshots through `get_dirty`. Both `original_is_equivalent` and `_read_cast`
treat `NO_VALUE` as "no original" (genuinely dirty / passthrough) rather than feeding the
sentinel into a coercer (which crashed the decimal cast).

---

## § 4 — Enum and extended built-in casts

**Originally**: ADR-054

Status: Accepted (delivered WI-arvel-017)

Eloquent-parity increment (backlog `006`, story S6). Extends the `__casts__` pipeline with
backed enums, `object`, `collection`, and `datetime:FORMAT`. No schema or route changes.

### ADR-007 § 4-01: An `Enum` subclass is a valid cast spec

Status: Accepted

`__casts__` already accepted a cast string or a `CastsAttributes` class/instance. We add a
third form: a Python `Enum` subclass passed directly (`"status": Status`). It resolves to a
`_ResolvedCast` where read returns the member (`Status(value)`), write stores the backing value
(`member.value`, or `Status(raw).value` for a raw input), and serialize emits the backing value.
Invalid values raise `ValueError` at write time — same fail-fast contract as the other casts.

We pass the enum **class** rather than a `"enum:Status"` string because Python has no global
class registry to resolve a name against, and a direct reference is type-checkable.

### ADR-007 § 4-02: `object` and `collection` are read-path-only, like `array`

Status: Accepted

`object` decodes JSON into a `SimpleNamespace` (attribute access); `collection` decodes into an
Arvel `Collection`. Both join `dict`/`list`/`array` in `_WRITE_SKIP_CASTS`: coercing to an
in-memory object on write would break INSERTs into a `String`/JSON column. The stored value
stays the raw assignment; the read transforms it.

Serialization can't leave a `Collection`/`SimpleNamespace` in `to_dict()` output, so both get a
built-in serializer (`_BUILTIN_SERIALIZERS`): `collection` → plain `list`, `object` → plain
`dict`. These run in `to_dict` after the read cast, matching Eloquent's `SerializesCastable`.

### ADR-007 § 4-03: `datetime:FORMAT` parses with a fallback and serializes with `strftime`

Status: Accepted

`"datetime:%Y-%m-%d %H:%M"` reads by trying `strptime(value, FORMAT)` first, falling back to the
shared ISO-8601 coercer (`_to_utc_datetime`) when the input doesn't match the format — so a DB
column holding ISO timestamps still hydrates. Naive results are pinned to UTC. Serialize emits
`dt.strftime(FORMAT)`. Write reuses the read coercer so assignment normalizes to a `datetime`.

### ADR-007 § 4-04: serialize skips `None`

Status: Accepted

`to_dict` previously called a cast's `serialize` for every listed key present in the row,
including unset (`None`) columns. The new built-in serializers (`list`, `strftime`) aren't
None-safe, so `to_dict` now skips serialize when the value is `None` — symmetric with the read
path, which already passes `None` through untouched.

---

## § 5 — Declarative encrypted casts + app `Encrypter`

**Originally**: ADR-055

Status: Accepted (delivered WI-arvel-018)

Eloquent-parity increment (backlog `006`, story S3). Adds an app-level encrypter and
`"encrypted[:variant]"` cast specs. Touches PII handling — recorded with a security note.

### ADR-007 § 5-01: A new app `Encrypter`, separate from column-level `EncryptedType`

Status: Accepted

`database.casts.EncryptedType` is a SQLAlchemy `TypeDecorator` configured per column with an
explicit key (wire format v1, `key_id`-tagged for rolling migrations). The declarative cast
needs an **app-wide** encrypter keyed from `APP_KEY`, so we add `arvel.encryption.Encrypter`
(AES-256-GCM) with its own wire format (v2: `b64(VERSION || IV(12) || ct+tag)`). The two never
collide on disk because the version byte differs.

The 32-byte key is HKDF-SHA256-derived from the raw `APP_KEY` bytes (any length, `base64:`
prefix accepted), with `info=b"arvel-encrypter"` — the same derivation style the cookie session
store and URL signer already use. IV is random per write, so equal plaintexts produce different
ciphertexts (not searchable by equality, by design).

### ADR-007 § 5-02: `Crypt` facade caches per `APP_KEY`

Status: Accepted

`arvel.facades.Crypt` builds the encrypter lazily from `os.environ["APP_KEY"]` and caches it in a
dict keyed by the raw key string — so a rotated or test-monkeypatched key transparently rebuilds.
`Crypt.set_encrypter(enc)` pins one for tests; `set_encrypter(None)` reverts. A missing `APP_KEY`
raises `MissingAppKeyError` rather than silently using a zero key.

### ADR-007 § 5-03: Cast variants and the read/write/serialize contract

Status: Accepted

`_make_encrypted_cast(param)` handles `encrypted` (param `""`/`string`), `encrypted:json`,
`encrypted:array`, `encrypted:object`, `encrypted:collection`. Unknown variants raise at class
definition time.

- write: `string` → `encrypt_string(str(value))`; the others JSON-encode then encrypt
  (`Crypt.encrypt`). A `SimpleNamespace` is unwrapped to its `__dict__` first; `dict`/`list`
  (including `Collection`, a `list` subclass) pass straight to `json.dumps`.
- read: `string` → `decrypt_string`; the others decrypt then decode, with `object` →
  `SimpleNamespace` and `collection` → `Collection`.
- serialize: `object` → plain `dict`, `collection` → plain `list`; the rest need none (decrypted
  string/list/dict are already JSON-friendly).

Because reads decrypt, `to_dict()` exposes the **decrypted** value — matching Eloquent's
`toArray`. Use `__hidden__` to keep secrets out of serialized output. Cast-aware dirty tracking
compares decrypted values, so re-encrypting an unchanged value (new IV → new ciphertext) is
correctly seen as not dirty.

---

## § 6 — EncryptedType: AES-GCM with random + deterministic modes

**Originally**: ADR-056 · Date: 2026-05-17

### Context

`EncryptedType` lets developers store sensitive data (SSNs, API keys,
private notes) encrypted at rest. Two patterns are needed:

1. **Random mode** (default): each write uses a fresh random IV. Resulting
   ciphertexts are different for the same plaintext. Maximally secure but
   not searchable by exact equality.
2. **Deterministic mode** (opt-in): each write uses an IV derived from the
   row's PK + a per-column salt. Same plaintext on the same row → same
   ciphertext, so a `WHERE col = ?` against the encrypted column works for
   exact-match queries. Leaks equality but enables search.

Options for the AEAD primitive:

| Option | Pros | Cons |
|---|---|---|
| A. `cryptography.fernet` (AES-128-CBC + HMAC) | Easiest API | 128-bit key only; padded ciphertext leaks length; deterministic mode unnatural |
| B. **`cryptography.hazmat.primitives.ciphers.aead.AESGCM`** | 256-bit; AEAD (integrity for free); efficient; standard | Lower-level — we own the IV / AAD logic |
| C. `nacl.secret.SecretBox` (XSalsa20-Poly1305) | Simple | Different cipher family than the rest of the ecosystem; deterministic mode harder |

### Decision

Option B — **AES-GCM via `cryptography`**, 256-bit key.

**Wire format (shipped in WI-003 with Stage 4b hardening)**:

```
b64( VERSION(1) || KEY_ID_LEN(1) || KEY_ID(N) || IV(12) || CT_WITH_TAG )
```

- `VERSION = 0x01` — single byte, lets future formats coexist on disk during a rolling
  migration.
- `KEY_ID` — ASCII string identifying which key was active when the row was
  written. Defaults to `"v1"`. Mismatched key-ids raise
  `DecryptionError` (never silent corruption).
- `IV` — 12-byte AES-GCM nonce (see modes below).
- `CT_WITH_TAG` — ciphertext concatenated with the 16-byte GCM tag.
- Optional `associated_data` is passed to GCM as AAD; recommended pattern
  is `EncryptedType(key, associated_data=f"{table}.{column}".encode())` so
  ciphertext copied from a different column fails to decrypt.

**Random mode (default)**:
- Generate 12-byte IV via `os.urandom(12)`.
- Encrypt: `aesgcm.encrypt(iv, plaintext, associated_data=aad)`.

**Deterministic mode (`deterministic=True`)**:
- IV: `SHA256(key || plaintext)[:12]`. Same plaintext → same IV → same
  ciphertext. Exact-match searchable but leaks equality.
- Same AAD discipline applies — copied ciphertext from another column
  still fails to decrypt.

**Key sourcing**:
- Master key: `settings.app.secret_key` (`SecretStr`, 32 bytes from URL-safe
  Base64; if shorter, HKDF-expand to 32).
- Per-column derived key:
  `HKDF(SHA256, length=32, salt=column_salt, info=f"col:{table}.{column}").derive(master)`.
- `column_salt` is a static 16-byte value compiled into the model class
  (auto-derived from a stable hash of `f"{table}.{column}"`).

**Key rotation**:
- Document the procedure in `docs/concepts/arvent.md`. Outline:
  1. Add `secondary_key` config field.
  2. On read, try primary key first; fall back to secondary.
  3. Run `arvel db:rotate-encryption <model>.<col>` (WI-004) to re-encrypt
     all rows with the primary key.
  4. Remove `secondary_key` once rotation completes.
- Until WI-004 ships the CLI helper, rotation is manual via a one-off script.
  The DSL primitives (`for row in await Model.all(): row.col = row.col; await row.save()`) make this trivial.

### Consequences

**Positive**:
- Standard, well-vetted AEAD cipher.
- Random mode is genuinely random (different ciphertexts per write).
- Deterministic mode is searchable for the narrow use case (e.g. encrypted
  emails for lookup).
- Decryption with the wrong key raises `cryptography.exceptions.InvalidTag` →
  we wrap as `DecryptionError`. Never silent corruption.

**Negative**:
- Deterministic mode leaks equality. Users opt in; docs are explicit.
- Master key rotation is non-trivial — it's an O(N rows) operation; that's
  inherent, not a flaw of our design.
- `settings.app.secret_key` becomes critical: losing it means losing the
  encrypted data. Documented as such; users are expected to back it up like
  a database master credential.

**Enforcement**:
- `tests/security/test_encrypted_wire_format.py` covers the versioned wire
  format, key-id binding, AAD binding, and the random/deterministic mode
  invariants (random ≠ deterministic, deterministic stable).
- Wrong-key/tampered-ciphertext failures raise `DecryptionError`, never
  return garbage.
- The rotation CLI (`arvel encryption:rotate`) ships in the
  wire format above is rotation-ready (key-id on disk identifies which
  key wrote each row).

---

## § 7 — `hashed` Cast and Explicit Mass-Assignment Bypass

**Originally**: ADR-057

Status: Accepted

Eloquent-parity increment (backlog `006`, Sprint A: story S2). Touches credential
hashing → Risk Tier 3, so a Stage 4b security review accompanies it.

### ADR-007 § 7-01: `hashed` is a write-only cast over the existing `__casts__` dispatch

Status: Accepted

`__casts__` maps a column to one coercer applied on both read and write. A `hashed`
cast must hash on **write** and pass the stored digest through unchanged on **read**
(re-hashing a hash on every attribute access would corrupt it). So `hashed` joins
the dispatch table but is also added to a new `_READ_SKIP_CASTS` set — the mirror of
the existing `_WRITE_SKIP_CASTS` (read-only JSON casts). `__getattribute__` skips
read-skip casts; `__setattr__` applies them.

The coercer hashes via the project `Hash` facade (argon2id by default — never a weak
hash) and is **idempotent**: a value already shaped like an argon2 (`$argon2…`) or
bcrypt (`$2…`) digest passes through untouched, so re-saving a loaded model doesn't
double-hash.

### ADR-007 § 7-02: `force_fill` bypasses guards; `unguarded()` is a scoped context only

Status: Accepted

`force_fill(**attrs)` assigns every attribute through `__setattr__` (so mutators and
casts still run) without the `__fillable__`/`__guarded__` check — for trusted seed and
admin flows.

`Model.unguarded()` is a **synchronous, re-entrant context manager** backed by a
`ContextVar`; `_check_mass_assignment` early-returns while it's active. We deliberately
do **not** ship Laravel's global `unguard()` / `reguard()` toggle: an un-paired
`unguard()` silently disables mass-assignment protection process-wide, which directly
contradicts the security requirement that bypass be explicit and bounded. The scoped
context manager gives the same capability with guaranteed restoration.

Both bypasses are opt-in and must never wrap untrusted request data — enforced by
review, documented at the call sites.

---

## § 8 — Re-entrant Event Suppression and Quiet Persistence

**Originally**: ADR-058

Status: Accepted

Eloquent-parity increment (backlog `006`, Sprint A: story S7). No HTTP or schema
surface — recorded as an ADR.

### ADR-007 § 8-01: Suppress events with a `ContextVar`, not a per-model flag

Status: Accepted

Laravel mutes its event dispatcher globally for `withoutEvents`. Arvel fires events
from async persistence methods (`save`, `delete`, `restore`, `force_delete`, plus
`create`), so suppression must survive `await` boundaries and stay isolated per
asyncio task. A module-level `ContextVar[bool]` does exactly that — each task/copy
sees its own suppression state, with no cross-task leakage that a class attribute or
plain global would cause under concurrency.

`without_events()` is an `@asynccontextmanager` that `set()`s the var and `reset()`s
it with the returned token on exit. Token reset (not `set(False)`) makes nesting
**re-entrant**: an inner block restores the outer block's `True`, and only the
outermost exit returns to `False`. `fire_async`, `fire_cancellable`, and
`fire_after_commit` early-return when the var is set — so cancellable before-hooks
can't abort a write inside the block either.

### ADR-007 § 8-02: `*_quietly` helpers wrap the existing methods in the context

Status: Accepted

`save_quietly`, `delete_quietly`, `force_delete_quietly`, `restore_quietly`, and
`update_quietly` are thin wrappers that run the normal persistence path inside
`without_events()`. No duplicated persistence logic — the quiet variants can't drift
from their loud counterparts. `update_quietly(**attrs)` fills then saves quietly,
mirroring Laravel's `updateQuietly` (Arvel has no separate instance `update`).

---

## § 9 — Static event registration + custom event objects

**Originally**: ADR-059

Status: Accepted (delivered WI-arvel-020)

Eloquent-parity increment (backlog `006`, story S9). Adds three ways to wire model lifecycle
hooks without authoring a full observer class. No schema or route changes.

### ADR-007 § 9-01: `Model.on(event, callback)` wraps the observer machinery

Status: Accepted

Laravel exposes `Model::created(fn)`, `Model::saving(fn)`, etc. We collapse these to a single
`Model.on("created", cb)` classmethod. Rather than introduce a parallel callback registry, `on`
wraps the callable in a one-event `_CallbackObserver` and appends it to the same observer list
`Model.observe(...)` uses. So callbacks and observer-class methods run through the identical
dispatch path: cancellable before-hooks (`creating`/`updating`/`deleting`/`restoring`) honor a
`False` return, and async callables are awaited. One code path, no second dispatch loop to keep
in sync.

```python
User.on("created", lambda u: log.info("created %s", u.id))
User.on("creating", lambda u: False)  # aborts the insert
```

### ADR-007 § 9-02: `__dispatches_events__` maps lifecycle names to bus events

Status: Accepted

`__dispatches_events__ = {"created": UserCreated}` dispatches a custom event object on the app
event bus (the `Event` facade) when that lifecycle fires — Eloquent's `$dispatchesEvents`. The
mapped class subclasses `ModelEvent`, a frozen Pydantic `Event` with `arbitrary_types_allowed`
carrying the model instance under `.model`. Dispatch happens after the observer loop in both
`fire_async` and `fire_cancellable`.

When no dispatcher is bound (pure-DB unit tests with no `EventServiceProvider`), dispatch is
**silently skipped** rather than raising `FacadeNotBoundError`. Model persistence shouldn't hard
-depend on the event subsystem being booted; the mapping is an opt-in integration, not a
requirement.

### ADR-007 § 9-03: `__observed_by__` auto-registers at class-definition time

Status: Accepted

`__observed_by__ = [AuditObserver]` registers each observer in `Model.__init_subclass__`, the
Python equivalent of Laravel's `#[ObservedBy(...)]` attribute. It reads from `cls.__dict__`
(not inherited) so a subclass declaring its own list doesn't double-register a parent's
observers. Registration reuses `bind_observer`, so container-resolved observers and no-arg
observers behave exactly as with an explicit `observe()` call.

### ADR-007 § 9-04: `ModelEvent` is defined directly, not via a factory

Status: Accepted

An earlier draft built `ModelEvent` lazily through a factory function to avoid importing pydantic
at `events.py` import time. That made `ModelEvent`'s static type `Any`, which blocks
`class UserCreated(ModelEvent)` under strict type checking ("cannot subclass Any"). Since
`arvel.events.event` only pulls in pydantic (no database import — no cycle), `ModelEvent` is now a
plain top-level class. Subclassing type-checks, and the registry auto-registration in
`Event.__init_subclass__` still fires.

---

## § 10 — Timestamp controls

**Originally**: ADR-060

Status: Accepted (delivered WI-arvel-021)

Eloquent-parity increment (backlog `006`, story S12). Adds opt-out, custom column names,
`touch`/`touch_quietly`, and a `without_timestamps` block. No schema change to existing models.

### ADR-007 § 10-01: Hook attachment moves to `Model.__init_subclass__`

Status: Accepted

The `created_at`/`updated_at` auto-fill previously lived in `Timestamps.__init_subclass__`, which
hard-coded the column names. To support custom columns and opt-out, hook attachment moves to
`Model.__init_subclass__`. It attaches the `before_insert`/`before_update` mapper events only when
`__timestamps__` is truthy **and** the model actually has the attribute named by `CREATED_AT` or
`UPDATED_AT`. So a plain model without timestamp columns pays nothing, the `Timestamps` mixin works
as before (it just supplies the default columns), and a model declaring its own timestamp columns
gets auto-fill without the mixin.

### ADR-007 § 10-02: `CREATED_AT` / `UPDATED_AT` constants + `__timestamps__` toggle

Status: Accepted

Three `ClassVar`s on `Model`: `__timestamps__: bool = True`, `CREATED_AT: str = "created_at"`,
`UPDATED_AT: str = "updated_at"` (Eloquent's `$timestamps`, `CREATED_AT`, `UPDATED_AT`). The mapper
hooks read the constants — they're declared `str` so `cls.CREATED_AT` type-checks without a
`getattr` widening to `Any`. Setting `__timestamps__ = False` skips hook attachment entirely; the
columns (if present) stay `None` and must be nullable or you'll hit a NOT NULL error — that's the
point of opting out.

SQLAlchemy maps columns to Python attribute names, so "custom column" means a custom attribute
(`inserted_at`) that the developer declares; the constant tells the hooks which attribute to fill.

### ADR-007 § 10-03: `without_timestamps()` is a task-local async context

Status: Accepted

`Model.without_timestamps()` returns an async context manager backed by a `ContextVar`
(`_suppress_timestamps`), mirroring `without_events()`. The mapper hooks read the var, so any insert
or update flushed inside the block skips auto-fill. A `ContextVar` (not a plain flag) keeps the
suppression isolated per asyncio task and intact across `await` boundaries — flushes happen during
the awaited `create()`/`save()`, still inside the block. Used for imports and backfills where the
caller supplies explicit timestamps.

### ADR-007 § 10-04: `touch(attribute=None)` saves through the event path

Status: Accepted

`touch()` sets `UPDATED_AT` (or a named column) to now and calls `save()`, so it fires
`saving`/`updated`/`saved` and the `before_update` hook still bumps `UPDATED_AT` — Eloquent's
`touch()` parity, including the optional attribute form (`touch("published_at")`).
`touch_quietly()` wraps it in `without_events()`, matching the other `*_quietly` helpers.

---

## § 11 — Distinct soft/hard-delete and replicate events

**Originally**: ADR-061

Status: Accepted (delivered WI-arvel-023)

Eloquent-parity increment (backlog `006`, story S11). Lets listeners tell a soft delete from a hard
delete and react to clones. No schema change.

### ADR-007 § 11-01: `trashed` fires on soft delete, alongside `deleted`

Status: Accepted

Soft `delete()` now fires `trashed` then `deleted` (Eloquent order). `deleted` still fires for both
soft and hard deletes — code that just wants "a row went away" keeps working — while `trashed`
fires *only* on the soft path, so a listener can react to the soft-delete specifically. Added to
`_ASYNC_EVENTS` (non-cancellable; the row is already marked by the time it fires).

### ADR-007 § 11-02: `force_deleting` / `force_deleted` wrap hard deletes

Status: Accepted

`force_delete()` fires `force_deleting` → `deleting` → (hard DELETE) → `deleted` → `force_deleted`,
matching Laravel's `forceDelete()` which delegates to `delete()` between the force hooks. Both
before-hooks are cancellable (`False` aborts); `force_deleting` is in `_CANCELLABLE_EVENTS`.
`trashed` never fires on this path — that's the signal that distinguishes hard from soft. A model
without `SoftDeletes` has no separate `force_delete` override, so it gets the full set too; harmless,
and consistent.

### ADR-007 § 11-03: `replicating` fires on the clone

Status: Accepted

`replicate()` fires `replicating` on the *new* instance (not the source) just before returning it,
matching Eloquent — listeners can scrub or seed fields on the copy. Non-cancellable.

### ADR-007 § 11-04: Bulk QueryBuilder deletes stay event-free

Status: Accepted

The story AC mentioned bulk-QB soft deletes firing `trashed`. We deliberately don't: per ADR-008 § 3 and
real Eloquent, bulk writes (`query().delete()`, `restore()`, `force_delete()`) are set-based
UPDATE/DELETE statements that never load rows, so there are no instances to fire per-row events on.
Firing fabricated events would be a divergence from Laravel, not parity. Listeners that need per-row
delete events operate on instances. Documented here so the AC gap is intentional, not an oversight.

---

## § 12 — Factory enhancements

**Originally**: ADR-062

Status: Accepted (delivered WI-arvel-023... WI-arvel-024)

Eloquent-parity increment (backlog `006`, story S13). Brings `Factory` closer to Laravel's
`HasFactory` surface: M2M attachment, soft-deleted state, Faker in callbacks, quiet creation, and
per-connection persistence. No schema change.

### ADR-007 § 12-01: `has_attached(relation, factory, *, count, pivot)`

Status: Accepted

After the parent is flushed, the related factory builds `count` rows and each is linked through the
`BelongsToMany` accessor's `attach(pk, **pivot)`. `pivot` columns are written on every pivot row.
Children are created via `create()` so their own `has`/`has_attached`/callbacks run too. We don't
`session.expire` the relation afterwards (unlike `has()` for true `relationship()`s) — the
`BelongsToMany` accessor isn't a mapped attribute, and `attach()` already invalidates its eager
cache.

### ADR-007 § 12-02: `trashed()` state

Status: Accepted

Sets the soft-delete column (`__arvel_soft_delete_column__`, default `deleted_at`) to now on each
made instance, after construction — the column is `init=False`, so it can't go through `__init__`.
Raises `AttributeError` if the model lacks `SoftDeletes`, matching the rest of the soft-delete API.
The row persists already-trashed (hidden by the default scope, visible via `with_trashed()`).

### ADR-007 § 12-03: Faker passed to callbacks

Status: Accepted

`after_making` / `after_creating` callbacks now receive a shared `faker.Faker` instance as the
second argument instead of `None`. Faker is a dev-only dependency, so `_faker()` imports it lazily
and caches the instance (in a one-slot list to dodge the constant-redefinition lint); if it's not
installed, callbacks get `None` as before. The callback contract `(_, faker)` is unchanged.

### ADR-007 § 12-04: `create_quietly()`

Status: Accepted

Wraps `create()` in `without_events()` so any model lifecycle events triggered during the build
(children, attached rows, observers on the created models) are muted — Laravel's `createQuietly`.

### ADR-007 § 12-05: `connection(name)` per-factory routing

Status: Accepted

Records a named connection; `create()` opens a session from `DB.session_maker_for(name)`, binds it
as the active session for the whole build (so children and pivot attaches use it too), commits, and
restores the previous session. Added `DB.session_maker_for()` (public maker lookup, reused by
`DB.connection()`) and `DB.forget_named()` (drop a registration, used by tests). Without a name, the
ambient session is used — unchanged default.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-051 | — | Unified `Attribute` descriptor | § 1 |
| ADR-052 | — | Attribute-level Custom Cast Protocol | § 2 |
| ADR-053 | — | Cast-aware Dirty Tracking | § 3 |
| ADR-054 | — | Enum and extended built-in casts | § 4 |
| ADR-055 | — | Declarative encrypted casts + app `Encrypter` | § 5 |
| ADR-056 | 2026-05-17 | EncryptedType: AES-GCM with random + deterministic modes | § 6 |
| ADR-057 | — | `hashed` Cast and Explicit Mass-Assignment Bypass | § 7 |
| ADR-058 | — | Re-entrant Event Suppression and Quiet Persistence | § 8 |
| ADR-059 | — | Static event registration + custom event objects | § 9 |
| ADR-060 | — | Timestamp controls | § 10 |
| ADR-061 | — | Distinct soft/hard-delete and replicate events | § 11 |
| ADR-062 | — | Factory enhancements | § 12 |
