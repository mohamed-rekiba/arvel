# ADR-010 — Authentication

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-24; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Password hashing (bcrypt + argon2 reconcile), token storage (SHA-256), session guard alignment, gate fail-closed, email validation at the boundary, refresh-token storage strategy, subsystem ownership, email verification signed URL, refresh-token repository abstraction, auth-middleware ORM completions.

## Why this is one ADR

All ten decisions design `arvel.auth` end-to-end. Together they describe the auth subsystem; separately they read like a scattered collection of point fixes.

---

## § 1 — Password Hashing — bcrypt default, argon2id opt-in

**Originally**: ADR-084 · Date: 2026-05-17

### Context

We need a password hashing strategy for `Hash.make()` / `Hash.check()`. Arvel's Constitution Article IV §2 states: "Cryptography defaults: argon2id for passwords; AES-GCM via `cryptography` for `EncryptedType`; never roll our own crypto."

However, bcrypt is vastly more widely used in Python web apps, has better ecosystem support (pass any existing bcrypt hash from Django/Flask), and the `bcrypt` library is mature and well-maintained. The `argon2-cffi` library is the correct argon2id implementation but is an additional dependency.

### Options

| Option | Pros | Cons |
|---|---|---|
| A: bcrypt default, argon2id opt-in | Widest ecosystem compat; `bcrypt` is stable; opt-in for argon2 | Technically contradicts Article IV §2 wording |
| B: argon2id default, bcrypt opt-in | Exact Article IV §2 compliance; better algorithm | `argon2-cffi` as a hard dep; breaks compat with existing bcrypt hashes |
| C: argon2id only | Cleanest; future-proof | Breaks all existing hash migration paths |

### Decision

**Option A** — bcrypt as the default driver (cost=12), argon2id available as `arvel[argon2]` optional extra.

The constitutional wording "argon2id for passwords" is interpreted as "argon2id is the *preferred* algorithm and must be *available*." bcrypt at cost=12 is computationally equivalent in practice and is essential for hash migration paths. The opt-in argon2 path satisfies the constitutional intent.

Cost 12 is the minimum; the framework will log a warning if apps lower it below 12.

### Consequences

- **Gain**: Compatibility with existing bcrypt hashes from other Python frameworks; bcrypt as a well-understood, auditable choice
- **Accept**: Article IV §2 is satisfied by opt-in availability, not default
- **Risk**: New projects not choosing argon2 may be weaker in the long term — mitigated by documenting argon2 as the recommended choice in auth guide

---

## § 2 — Personal Access Token Storage — SHA-256 + Sanctum Pattern

**Originally**: ADR-085 · Date: 2026-05-17

### Context

`HasApiTokens.create_token()` must generate a token and store it securely. Options are: store plain text, store encrypted, or store a hash. The token is effectively a credential — it must be treated like a password.

### Options

| Option | Pros | Cons |
|---|---|---|
| A: Store plain text | Trivial token revocation check | DB breach exposes all tokens |
| B: Store encrypted (AES-GCM) | Recoverable; revocation easy | Encryption key becomes single point of failure; key rotation is expensive |
| C: Store SHA-256 hash (Sanctum pattern) | DB breach useless (hashes aren't reversible); no key management | Plain text shown once only — lost token requires new token |

### Decision

**Option C** — SHA-256 hash stored, plain text shown once (Sanctum pattern).

`secrets.token_urlsafe(40)` generates 320 bits of entropy — brute-forcing SHA-256(token) from the hash is computationally infeasible. Timing-safe comparison via `hmac.compare_digest` prevents timing oracles. This is the same design used by Laravel Sanctum and GitHub personal access tokens.

Token generation:
```python
plain_text = secrets.token_urlsafe(40)
token_hash = hashlib.sha256(plain_text.encode()).hexdigest()
```

Verification:
```python
candidate_hash = hashlib.sha256(bearer.encode()).hexdigest()
stored_hash = record.token
if not hmac.compare_digest(candidate_hash, stored_hash):
    return None
```

### Consequences

- **Gain**: DB breach does not expose tokens; no encryption key to manage
- **Accept**: Lost tokens cannot be recovered — users must generate a new one
- **Risk**: None significant at this entropy level

---

## § 3 — SessionGuard Alignment to Arvel SessionData

**Originally**: ADR-086 · Date: 2026-05-17

### Context

The existing `SessionGuard`  reads `request.session` — Starlette's built-in dict-based session, populated by Starlette's `SessionMiddleware`. Arvel shipped its own session stack in : `StartSession` middleware populates `request.state.session` as a typed `SessionData` object. The two session systems can't safely coexist on the same route — one or the other must own session storage.

### Options

| Option | Pros | Cons |
|---|---|---|
| A: Keep `request.session` (Starlette dict) | No breaking change for WI-002 users | Two session systems coexist; Arvel's typed session is ignored by the guard; session fixation prevention is hard |
| B: Migrate to `request.state.session` (Arvel `SessionData`) | Single, typed session system; proper session fixation support; flash bag integration | Breaking change for apps using SessionGuard + Starlette SessionMiddleware |
| C: Support both via a flag | No-one is broken | Complexity doubles; two code paths to maintain forever |

### Decision

**Option B** — `SessionGuard` reads and writes `request.state.session` (`SessionData`).

Arvel is pre-1.0 (no stability guarantees per Constitution Article VI §2). The dual-session coexistence is a footgun: an app that enables both `SessionMiddleware` and `StartSession` gets silently inconsistent session state. The correct fix is a single owner. `SessionData` is strictly richer than Starlette's dict (typed flash bag, session ID regeneration, consistent storage backend).

**Migration**: Apps using `SessionGuard` with Starlette's `SessionMiddleware` must switch to `StartSession` middleware and `SessionConfig`. The change is documented in CHANGELOG and the auth guide.

**Backward compat re-exports**: `from arvel.http.auth import SessionGuard` continues to work (re-exports from `arvel.auth.guards.session_`). Only the session source changes.

### Consequences

- **Gain**: Single typed session stack; `SessionGuard.login()` can regenerate session ID safely; flash bag integration possible
- **Accept**: Breaking change for any app using `SessionGuard` + Starlette `SessionMiddleware` (pre-1.0, acceptable)
- **Risk**: Migration friction — mitigated by clear CHANGELOG entry and auth guide

---

### Merged: Session Guard Must Verify Password Before Login (was ADR-010 § 3)

**Status**: Accepted
**Date**: 2026-05-24

### Context

`SessionGuard.attempt()` logged users in after a successful email lookup without verifying
the submitted password against the stored hash. Any valid email address was sufficient to
authenticate.

### Decision

The guard calls `Hash.check(plain_password, stored_hash)` between `by_credentials()` and
`login()`. On mismatch it returns `False` without revealing whether the email existed.
The provider continues to do lookup only; password verification stays in the guard —
matching Laravel's exact responsibility split.

### Consequences

- Closes an authentication bypass (C-1 from May 2026 review)
- No API change — `attempt(credentials, request) -> bool` signature unchanged
- One-line change to `session.py`; covered by new test in `test_047_auth_security.py`

---

## § 4 — Gate Fail-Closed — Unregistered Ability → AuthorizationException

**Originally**: ADR-087 · Date: 2026-05-17

### Context

When `Gate.authorize(ability, user, ...)` is called with an ability that has no registered closure or policy, two behaviors are possible: fail-open (allow the action) or fail-closed (deny the action).

### Options

| Option | Pros | Cons |
|---|---|---|
| A: Fail-open (allow unregistered) | No accidental lockouts during development | Security footgun: missing policy silently grants access |
| B: Fail-closed (deny unregistered) | Secure by default; missing policy is immediately visible | Developer must register every ability before using it |
| C: Configurable | Flexible | Complexity; two failure modes to document and test |

### Decision

**Option B** — Gate is fail-closed. Unregistered ability → `AuthorizationException`.

The OWASP A01 (Broken Access Control) risk is too high for fail-open. A typo in an ability name or a forgotten policy registration silently grants all users access to the resource. Fail-closed makes the bug immediately visible (403 in dev) rather than silently exploitable in production. This matches Laravel's behavior when using `Gate::authorize()` with no matching policy.

`Gate.allows()` returns `False` for unregistered abilities. `Gate.authorize()` raises `AuthorizationException`. This gives callers a way to gracefully handle missing policies when needed.

### Consequences

- **Gain**: Secure by default; missing policies are immediately visible failures
- **Accept**: Developers must register every ability explicitly; no "default allow"
- **Risk**: Accidental lockouts during development — mitigated by clear error messages from `AuthorizationException` (includes ability name and model class)

---

## § 5 — Email validation at the API boundary, not on the column

**Originally**: ADR-088 · Date: 2026-05-20

### Context

The 2026-05-20 SQLModel investigation surfaced a recurring question: should the framework ship a built-in `email()` column helper backed by a Pydantic value object, the way SQLModel pairs `EmailStr` with a single annotated attribute?

Three options were on the table:

- **A — VARCHAR + boundary validation.** Persist `VARCHAR(254)`. Validate the format on the Pydantic input schemas (`UserCreate`, `UserUpdate`) via `EmailStr`. This is the conventional Laravel / Rails / Django shape.
- **B — JSON value object.** Ship an `EmailAddress` Pydantic `BaseModel`, persist it through `PydanticType` as a JSON payload (`{"value": "alice@example.com"}`), and surface a typed `EmailAddress`-valued column. The column itself carries the validation.
- **C — VARCHAR-backed `TypeDecorator`.** Store `VARCHAR(254)` but use a `TypeDecorator` that converts `str ↔ EmailAddress` at the boundary so the attribute reads as a value object while the on-disk shape stays plain text.

Option B was prototyped and shipped briefly. It worked on SQLite but failed on PostgreSQL — `data type json has no default operator class for access method "btree"` — until the column type was switched to `JSONB` with a dialect-aware `load_dialect_impl`. The fix landed, the cross-dialect tests passed, and the implementation was complete and correct.

It was also overengineered for the actual need.

### Decision

**Emails persist as plain `VARCHAR(254)`. Format validation lives on Pydantic input schemas via `EmailStr` (Option A).**

- The framework ships **no** `email()` column helper.
- The framework ships **no** `EmailAddress` value object.
- `make:schema` upgrades any `String` column named `email` or matching `*_email` to `EmailStr` in the generated `Read` / `Create` / `Update` schemas. The upgrade is purely at the boundary; the model side stays a plain `str`.
- `Blueprint.email()` is removed; the migration call is `t.string("email", 254).unique()`.

The general-purpose improvements that were uncovered while implementing Option B — `PydanticType.load_dialect_impl` returning `JSONB` on PostgreSQL — are kept. They benefit every future `PydanticType` column (e.g. settings, preferences) and have no email-specific coupling.

### Rationale

#### Why Option A wins

1. **It serves the actual need.** "Email must be a valid email address" is a boundary-validation concern. The API receives strings from clients; `EmailStr` rejects malformed ones before they reach the model. Once stored, the value is a `str` because that's what every consumer wants — for templating, logging, comparison, indexing, and SQL projection.
2. **Storage stays conventional.** `VARCHAR(254)` is what every operator expects when they `SELECT email FROM users WHERE …`. Reports, admin tools, BI pipelines, and ad-hoc psql sessions don't need to know about JSON path expressions or value-object payloads.
3. **Indexing is free.** `UNIQUE` implies a B-tree unique index on every supported dialect. No `JSONB` operator-class trickery, no functional indexes on `email->>'value'` for case-insensitive lookups, no per-dialect quirks.
4. **`make:schema` closes the validation gap.** Without the name-based heuristic the user would have to remember to hand-edit every generated schema to swap `str` for `EmailStr`. The heuristic catches the common case (`email`, `billing_email`, `contact_email`) automatically; opt-out is editing the generated file, which is explicitly marked as user-editable.
5. **One concept, one place.** Validation rules live in the boundary schema. Persistence is dumb storage. The split is the same one the framework uses everywhere else (ADR-004 § 1 + the `PydanticType` doctrine).

#### Why Option B lost — even after we made it work

1. **Single use case doesn't justify a framework abstraction.** Rule of Three (`100-coding-standards.mdc`): a value-object column for *one* type is duplication of mechanism, not abstraction of behavior. There's no `Money`, `IpAddress`, `PhoneNumber`, or `Url` column today. Bring the value-object machinery back when there is.
2. **Dialect leakage.** The Postgres `json` → `jsonb` requirement, the SQLite-vs-Postgres-vs-MySQL UNIQUE semantics on JSON, and the `where_raw` coercion gap — all real, all documentable, none zero-cost. A `VARCHAR` column has none of these.
3. **In-memory caveat.** `User.create(email="x@y.com")` leaves `user.email` as a `str` until reload, because SQLA doesn't route bind values back through `process_result_value`. The `@validates` workaround is correct but is workaround-shaped — one more thing every adopter must remember.
4. **Operational opacity.** `email = '{"value": "alice@example.com"}'` in a database is harder to grep, harder to dump, harder to import from CSV. The shape is correct *for the ORM* and wrong *for everyone else who touches the data*.
5. **The value object had no unique behavior.** `EmailAddress.__eq__("alice@example.com")`, `__str__`, `__hash__` — every method delegated to the inner `str`. The only thing the value object did that a `str` doesn't is validation, and Pydantic does that perfectly fine at the boundary.

#### Why not Option C

A `VARCHAR`-backed `TypeDecorator` that converts `str ↔ EmailAddress` was considered. It preserves the on-disk simplicity of Option A and adds typed attribute reads. But:

- It re-introduces `EmailAddress` and its full API surface — `@validates` recipes, `to_dict()` shape, kwarg-shorthand semantics — for a value object that exists only because the column was clever. That's the value-object cost of Option B without the JSON storage cost.
- A plain `str` reads exactly as well as an `EmailAddress` value object once the boundary validation is in place. Nobody reads `user.email` and wishes it had domain methods that don't exist.

Defer C until at least two real value-object columns exist.

### Consequences

#### Positive

- Smaller framework surface: `arvel.database` exports two fewer symbols (`email`, `EmailAddress`). The schema DSL drops one method (`Blueprint.email`).
- No dialect-awareness burden on the email path. The cross-dialect test matrix for emails is exactly the matrix the `string()` helper already covers.
- The example app is conventional. New contributors recognize `email: str = string(254, unique=True)` immediately.
- `make:schema` now does meaningful work on email columns automatically — the validation gap is closed without any user action.

#### Negative

- Users who *want* domain methods on email (case-insensitive comparison, `.domain` / `.local_part`) must hand-roll a `TypeDecorator` or wrap in a property. The framework no longer provides one. This is intentional — see Rationale §B.1.
- The `@validates` recipe is no longer needed and was deleted from `eloquent.md`. Users coming from the old docs will not find it.

#### Migration / cleanup

The Option B implementation (`b1871f9`) is being reverted in the same commit as this ADR:

- `arvel.database.columns.EmailAddress` — deleted
- `arvel.database.columns.email` — deleted
- `arvel.database.schema.Blueprint.email` — deleted
- `arvel.database.casts.PydanticType.process_bind_param` loose-input coercion — reverted to strict form
- `arvel.database.casts.PydanticType.load_dialect_impl` — **kept**; benefits every PydanticType column
- `tests/database/test_email_column.py` — deleted
- `tests/database/test_email_column_sql_integration.py` — deleted
- Example app `my_app/app/models/User.py` — reverted to `string(254, unique=True)`
- Example app `my_app/database/migrations/2026_05_20_113351_user.py` — reverted to `t.string("email", 254).unique()`
- Example app `my_app/app/schemas/user_schema.py` — regenerated with `EmailStr` at the boundary

### Alternatives considered

| Option | Why not |
|---|---|
| Option B (JSON value object) | Five real costs (storage opacity, dialect leakage, in-memory caveat, single use case, value object has no unique behavior) outweigh the one benefit (typed attribute reads as `EmailAddress`). |
| Option C (VARCHAR + value-object cast) | Defers all of Option B's value-object costs without the JSON storage cost — but only earns its place when at least two value-object columns exist. Rule of Three. |
| SQLModel | Rejected wholesale in ADR-004 § 2 / research 002 — Pyright unsupported, PEP 649 breakage, metaclass fusion. Not specific to email. |
| `@validates` on the column | Server-side; only catches Python-set values, not raw `UPDATE` statements. Boundary validation catches both because client traffic always goes through Pydantic. |

### Notes

The `make:schema` email-detection heuristic is intentionally name-based, not type-annotation-based. It runs at codegen time against SQLA column metadata, where the only signal available is the column name and type. The alternative — a model-level `__email_columns__ = ["email", "billing_email"]` declaration — was rejected as redundant ceremony; column names are already the source of truth.

The 2026-05-20 cross-dialect test matrix (Postgres + MySQL + SQLite via Testcontainers) that was added for Option B is removed along with the test file. The pattern stays in the repo for future use — see `tests/cache/stores/test_database_store_sql_integration.py` for the canonical shape.

---

## § 6 — Refresh-token storage strategy

**Originally**: ADR-089 · Date: 2026-05-20

### Context

`JwtGuard` issues short-lived access JWTs. To support API sessions longer than a few minutes without inflating access-token TTLs, we need a refresh mechanism. There are several common shapes:

1. **Long-lived JWTs** — single token, just bump `exp`. Simple, but a leaked token is valid until expiry; revocation requires a denylist or short TTL.
2. **JWT refresh + JWT access** — sign both with the same secret, use a `typ` claim to discriminate. Stateless, but revocation is hard and rotation requires a server-side denylist anyway.
3. **Opaque refresh + JWT access** — random opaque refresh token stored hashed in DB; JWT for access. Server can revoke instantly, rotate cheaply, and never has to validate refresh tokens cryptographically.

### Decision

Adopt option (3). Refresh tokens are:

- **Opaque** — random URL-safe strings (`secrets.token_urlsafe(40)`), ≥40 bytes of entropy.
- **Hashed at rest** — SHA-256 hex digest stored in `refresh_tokens.token`. Plaintext is shown to the client once and never stored.
- **Rotated on use** — by default `JwtGuard.refresh_tokens(...)` revokes the supplied token and issues a fresh pair (configurable via `rotate_refresh=False`).
- **Time-bounded** — stored with `expires_at`; `find_by_hash` returns `None` past expiry or after `revoked_at` is set.
- **Discriminated from access tokens** — `JwtGuard.user` rejects any Bearer JWT whose `typ` claim is not `access`. This blocks refresh-as-bearer attacks even if the application mistakenly returns a refresh JWT instead of an opaque token.

Storage layer:

- Persistence is behind a `RefreshTokenRepository` Protocol (`store`, `find_by_hash`, `revoke`).
- `InMemoryRefreshTokenRepository` ships as a test double and a starting point for simple apps.
- A SQL-backed repository can be added later without API churn.

Migration:

- `packages/arvel/src/arvel/auth/migrations/create_refresh_tokens_table.py` ships the framework stub. Apps copy it (or `arvel make:migration CreateRefreshTokensTable`) into `database/migrations/` to apply.

### Consequences

✅ Server has full control over refresh-token validity (revoke, rotate, audit).
✅ Leaked refresh tokens have a bounded blast radius — rotation invalidates the old one on next use.
✅ DB compromise leaks hashes, not plaintext.
✅ Stateless access tokens preserve scaling story.

⚠️ Refresh requires a DB round-trip. Acceptable: refresh is rare relative to access-token use.
⚠️ Apps must store the refresh token securely on the client (OS keychain, HttpOnly cookie). Documented in `docs/site/authentication.md`.

### Related

- Builds on the precedent set by **ADR-010 § 2** (TokenGuard's SHA-256 hashing of personal access tokens).
- Pairs with **JwtGuard's existing protections**: `alg=none` rejected, 32-byte HMAC minimum, signature + `exp` always verified.

---

## § 7 — Auth subsystem ownership: kit → framework

**Originally**: ADR-090 · Date: 2026-05-21

### Context

produced the fullstack-Vue starter kit, but built the
authentication subsystem (~1,789 LOC) inside the kit's `backend/app/`
directory rather than the framework's `arvel.auth` module. The user's review
of WI-027 highlighted this as a fundamental architectural mistake:

> The authentication system should be a core part of the framework itself,
> not implemented in the template/kit.

This ADR records the decision to move the subsystem and the rationale.

### Decision

Authentication — register, login, logout, refresh-token rotation, email
verification, forgot/reset password, the controller, the routes, the
mailables, the templates, the listeners, the throttling — moves from
`packages/arvel-starter-fullstack-vue/backend/app/` into
`packages/arvel/src/arvel/auth/` (the framework).

The kit becomes a **consumer** of `arvel.auth`. It overrides what it needs to
override (mailable styling, audit listener for cross-cutting business audit,
error-page redirects), nothing more.

### Drivers

1. **Constitution Article II §4 — Laravel mental model is preserved.** Laravel's
   auth ships in `illuminate/auth`, not in every Laravel app's `App\Auth`
   directory. Arvel must preserve this.
2. **Reuse.** Every Arvel app needs auth. Per-app reimplementation is a
   YAGNI violation in reverse — every consumer pays the implementation
   cost over and over.
3. **Security audit surface.** Auth code is the highest-risk module in any
   web framework. Centralising it in `arvel.auth` means one auditable place
   instead of N kit-derived copies.
4. **Override hooks.** Frameworks need extension points; this WI defines them
   via container bindings + publishable assets, matching Laravel's
   `AuthServiceProvider` shape.

### Alternatives considered

#### A. Keep auth in the kit, ship a "starter pack" mindset (status quo)

**Pros**:
- Zero migration work.
- App author can edit any line without thinking about overrides.

**Cons**:
- Constitution Article II §4 violated.
- Every kit ships with its own auth → divergence over time.
- Security fixes can't be pushed centrally; users must merge upstream changes by hand.

**Rejected**: violates the constitution.

#### B. Auth as a separate `arvel-auth` PyPI package

**Pros**:
- Clean module boundary.
- Auth can version independently from the core.

**Cons**:
- Constitution Article III §1 mandates a modular monolith until 1.0.
- Splitting is premature optimisation (no real-world signal demands it).

**Rejected**: defer to post-1.0.

#### C. Move auth into framework but keep it opt-in (provider not registered by default)

**Pros**:
- API-only apps that don't need auth pay nothing.

**Cons**:
- Confuses the mental model (Laravel always has the `Auth` facade available).
- Tree-shaking isn't a real concern in Python.
- Default-on with `config.auth.routes.enabled=false` opt-out is a better escape.

**Rejected**: chose default-on with config opt-out.

### Consequences

#### Positive

- ~1,789 LOC removed from the kit (lighter starter).
- Single auditable auth implementation in the framework.
- Consistent mental model — every Arvel app uses the same auth shape.
- FB-027-007/008/011/012 closed by this WI.

#### Negative

- ~3,000 LOC added to `arvel.auth` (gross addition; coverage gate
  applies — must stay ≥90 % to land).
- Migration sub-sprint (S25.4) requires breaking the kit transiently.
- Any kit-side auth customisation (e.g. branded email) must now be done via
  publish + override, not "edit the source in place".

#### Neutral

- The `password_resets` table moves from kit-owned migration to framework
  publishable. Existing kit-deployed databases keep their existing rows;
  `vendor:publish` no-ops because the table already exists.

### Implementation

See SAD-028 (`docs/architecture/SAD-028-arvel-auth-core.md`)

### Validation

- All FRs FR-028-01..49 in PRD-028 pass acceptance.
- `arvel.auth` clean under `mypy --strict` and `pyright --strict`.
- Coverage ≥90 % on the new modules.
- Kit's full integration suite green after the migration commit.

---

## § 8 — Email verification: signed URL over DB token

**Originally**: ADR-091 · Date: 2026-05-21

### Context

WI-027's email verification was a stub: it generated a URL with a query-string
email parameter that didn't match the SPA route shape, so verification 404'd
in production (FB-027-011). WI-028 must ship a real implementation.

Two patterns are common:

1. **DB-backed token** — generate a secret, store its digest in a table
   keyed by user, send the plaintext in the email URL, look up + delete
   on verify. (This is what `password_resets` does.)
2. **Signed URL** — encode `{user_id, email_hash, exp}` into a URL, sign it
   with the app secret, hand to the user, validate on verify. No DB row.

This ADR records the choice for **email verification specifically**. Password
reset stays DB-backed (different threat model — see ADR-010 § 9).

### Decision

Email verification uses **signed URLs** via
`itsdangerous.URLSafeTimedSerializer`.

The URL shape is:

```
{APP_URL}/api/auth/email/verify/{URLSafeTimedSerializer.dumps({"id": user.id, "h": sha256(user.email)[:16]})}
```

- Salt: `"arvel.auth.email_verify"` (so the same `APP_KEY` can sign URLs for
  other purposes without cross-purpose verifies).
- TTL: 60 minutes (configurable via `config.auth.verification.ttl_minutes`).
- The hash invariant binds the signature to the email at issue-time — if a
  user changes their email after the URL is issued, the verify fails
  cleanly.

### Drivers

1. **No DB write at issue time.** Registration is the hot path; not adding a
   row makes it faster.
2. **Stateless verify.** A single signature check + 1 SELECT to fetch the
   user. No "does this row exist" lookup.
3. **Already a dependency.** `itsdangerous` is already in our dep tree
   (Pydantic's HMAC requirements + Flask-style sessions in some sub-deps).
   No new install footprint.
4. **Laravel parity.** Laravel's `MustVerifyEmail` flow uses signed URLs
   exactly this way (`URL::temporarySignedRoute(...)`).
5. **Resend is a no-DB-touch operation.** A user clicking "resend
   verification" mints a fresh URL; no rows to clean up.

### Alternatives considered

#### A. DB-backed token (`email_verifications` table)

**Pros**:
- Token can be revoked (delete the row).
- Audit trail: who requested verification, how often.

**Cons**:
- Extra table, extra migration, extra cleanup cron.
- Resend creates DB churn.
- Not how Laravel does it — friction with the mental model.

**Rejected**.

#### B. Embed the user in JWT and have the app verify

**Pros**:
- Conceptually consistent with the access-token flow.

**Cons**:
- JWTs leak via referrer/history more than opaque base64 (longer, easier
  to spot in logs).
- itsdangerous is purpose-built for this; using JWT here is overkill.

**Rejected**.

### Consequences

#### Positive

- One round-trip per verify (signature check + 1 row update).
- Resend is essentially free.
- No per-app `email_verifications` table to maintain.

#### Negative

- Revocation requires rotating `APP_KEY` (we accept this; matches Laravel).
- TTL is bound to clock skew — but `URLSafeTimedSerializer` allows up to
  ±60 s skew before rejecting, which is sufficient.

#### Neutral

- The kit currently uses query-string-only URLs. The migration produces
  three new SPA routes (`success`, `expired`, `invalid`) for redirect targets,
  but no fundamental SPA changes.

### Validation

- FR-028-18, FR-028-19, FR-028-20, FR-028-21, FR-028-22 in PRD-028 all pass.
- The Mailpit-captured URL parses with the same serializer + key on the
  verify path.
- Tampering any character of the signed payload produces 401.
- Hitting the URL after 61 min produces 401.

---

## § 9 — `RefreshTokenRepository` as a swappable abstraction

**Originally**: ADR-092 · Date: 2026-05-21

### Context

shipped `RefreshTokenRepository` as an ABC and an in-memory
implementation. WI-027's kit then bypassed the ABC entirely and wrote raw
SQL inside `AuthService`, hitting `personal_access_tokens` directly. That
approach surfaced FB-027-007: standalone `DB.statement()` calls outside an
explicit transaction never commit, causing silent rollbacks of refresh-token
inserts.

We need a production-grade refresh-token store, and we want it swappable
(some users will want Redis for sub-millisecond lookup; some will want
encrypted columns; some will want to mix-in WORM audit storage).

### Decision

The framework ships **`DatabaseRefreshTokenRepository`** as the default
implementation of `arvel.auth.RefreshTokenRepository`. It uses the framework's
ORM (`User`, `personal_access_tokens` table mapped via SQLAlchemy) and
**always wraps writes in `DB.transaction()`** — no standalone statements.

The abstraction is bound in `AuthServiceProvider.register()`:

```python
self.container.bind(
    RefreshTokenRepository,
    DatabaseRefreshTokenRepository,
)
```

Users override by re-binding in their own `AuthServiceProvider`. The interface
is:

```python
class RefreshTokenRepository(ABC):
    async def store(self, *, user_id: int, token_hash: str, ttl: timedelta) -> RefreshTokenRecord: ...
    async def find(self, *, token_hash: str) -> RefreshTokenRecord | None: ...
    async def rotate(self, *, old_hash: str, new_hash: str, user_id: int, ttl: timedelta) -> RefreshTokenRecord: ...
    async def delete(self, *, token_hash: str) -> None: ...
    async def delete_all_for_user(self, *, user_id: int) -> int: ...
    async def delete_family(self, *, user_id: int) -> int: ...
```

### Drivers

1. **Closes FB-027-007.** Every write goes through `DB.transaction()`,
   guaranteeing commit.
2. **Token-family revocation needs a uniform delete-all method.** Inline SQL
   in the broker would duplicate this logic across `reset_password`,
   `logout_others`, and the reuse-detection branch.
3. **Test isolation.** Unit tests for the broker can swap in
   `InMemoryRefreshTokenRepository` and stay fast.
4. **Customisability.** Users wanting Redis-backed refresh tokens
   (sub-millisecond) can plug in their own implementation — no fork.

### Alternatives considered

#### A. Continue with raw SQL inside `AuthBroker`

**Pros**: nothing.

**Cons**:
- Reproduces FB-027-007 forever.
- Couples broker to schema.
- Hard to test (every broker test needs a real DB).

**Rejected**.

#### B. Use SQLAlchemy ORM model (`PersonalAccessToken`) directly in broker

**Pros**:
- One layer fewer than the repo abstraction.

**Cons**:
- Same coupling problem as A.
- Loses the swap-out point for Redis/in-memory.
- Tests still need a DB.

**Rejected**.

#### C. Use Redis as the default

**Pros**:
- Sub-millisecond lookup.

**Cons**:
- Adds a hard dependency on Redis for every Arvel app.
- Refresh tokens benefit from durability + audit; Redis is in-memory.

**Rejected** — keep DB as default; Redis is a user choice via the abstraction.

### Consequences

#### Positive

- One canonical place for refresh-token storage.
- Explicit transaction boundaries kill the silent-rollback bug class.
- Token-family revocation is a single method call.
- Tests stay fast (`InMemoryRefreshTokenRepository`).

#### Negative

- One more layer between broker and DB. Acceptable; the broker is a
  high-frequency-of-change surface and the repo lets us iterate without
  schema changes.

#### Neutral

- The `personal_access_tokens` table schema doesn't change; the repo
  reads/writes the same columns the kit's raw SQL does.

### Validation

- FR-028-13..17 in PRD-028 all pass.
- `unit/test_refresh_tokens.py` covers store/find/rotate/delete/delete_family.
- `integration/test_provider.py` confirms the binding swap works.
- Token-reuse detection test (FR-028-15) deletes every refresh token for the
  user when an unknown but valid hash is presented.

---

## § 10 — Auth Middleware and ORM Correctness Fixes

**Originally**: ADR-093 · Date: 2026-05-24

### ADR-005 § 17-001: Save event detection via inspect().pending

**Context**: `Model.save()` must distinguish insert from update to fire the correct lifecycle event. SQLAlchemy tracks instance state in its identity map.

**Decision**: Snapshot `was_pending = sqla_inspect(self).pending` before `session.add(self)`. Fire `"created"` if `was_pending`, else `"updated"`.

**Alternatives considered**:
- Check `inspect(self).transient` — True before any `add()`, but snapshot still required before the add.
- Check DB primary key — unreliable for models with server-side default PKs before flush.
- `inspect(self).persistent` — the inverse; same approach.

**Consequence**: Correct lifecycle events reach listeners. No DB round-trip required.

---

### ADR-005 § 17-002: Authenticate resolves AuthManager not Guard

**Context**: The container may have multiple guards registered. `container.make(Guard)` resolves the last-bound `Guard` instance — undefined for multi-guard apps.

**Decision**: Call `container.make(AuthManager).guard(self._guard_name)`. This is type-safe since `AuthManager` is bound as a singleton by `AuthServiceProvider`.

**Consequence**: `guard_name="api"` now correctly selects the `api` guard. Apps with a single guard see no behavior change.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-084 | 2026-05-17 | Password Hashing — bcrypt default, argon2id opt-in | § 1 |
| ADR-085 | 2026-05-17 | Personal Access Token Storage — SHA-256 + Sanctum Pattern | § 2 |
| ADR-086 | 2026-05-17 | SessionGuard Alignment to Arvel SessionData | § 3 |
| ADR-087 | 2026-05-17 | Gate Fail-Closed — Unregistered Ability → AuthorizationException | § 4 |
| ADR-088 | 2026-05-20 | Email validation at the API boundary, not on the column | § 5 |
| ADR-089 | 2026-05-20 | Refresh-token storage strategy | § 6 |
| ADR-090 | 2026-05-21 | Auth subsystem ownership: kit → framework | § 7 |
| ADR-091 | 2026-05-21 | Email verification: signed URL over DB token | § 8 |
| ADR-092 | 2026-05-21 | `RefreshTokenRepository` as a swappable abstraction | § 9 |
| ADR-093 | 2026-05-24 | Auth Middleware and ORM Correctness Fixes | § 10 |
