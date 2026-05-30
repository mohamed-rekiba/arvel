# ADR-077 — Email validation at the API boundary, not on the column

**Status**: Accepted
**Date**: 2026-05-20
**Supersedes**: —
**Related**: ADR-011 (Eloquent-on-SQLA mixin), ADR-014 (`PydanticType` for value-object columns), ADR-076 (`MappedAsDataclass` for typed `__init__`)

## Context

The 2026-05-20 SQLModel investigation surfaced a recurring question: should the framework ship a built-in `email()` column helper backed by a Pydantic value object, the way SQLModel pairs `EmailStr` with a single annotated attribute?

Three options were on the table:

- **A — VARCHAR + boundary validation.** Persist `VARCHAR(254)`. Validate the format on the Pydantic input schemas (`UserCreate`, `UserUpdate`) via `EmailStr`. This is the conventional Laravel / Rails / Django shape.
- **B — JSON value object.** Ship an `EmailAddress` Pydantic `BaseModel`, persist it through `PydanticType` as a JSON payload (`{"value": "alice@example.com"}`), and surface a typed `Mapped[EmailAddress]` column. The column itself carries the validation.
- **C — VARCHAR-backed `TypeDecorator`.** Store `VARCHAR(254)` but use a `TypeDecorator` that converts `str ↔ EmailAddress` at the boundary so the attribute reads as a value object while the on-disk shape stays plain text.

Option B was prototyped and shipped briefly. It worked on SQLite but failed on PostgreSQL — `data type json has no default operator class for access method "btree"` — until the column type was switched to `JSONB` with a dialect-aware `load_dialect_impl`. The fix landed, the cross-dialect tests passed, and the implementation was complete and correct.

It was also overengineered for the actual need.

## Decision

**Emails persist as plain `VARCHAR(254)`. Format validation lives on Pydantic input schemas via `EmailStr` (Option A).**

- The framework ships **no** `email()` column helper.
- The framework ships **no** `EmailAddress` value object.
- `make:schema` upgrades any `String` column named `email` or matching `*_email` to `EmailStr` in the generated `Read` / `Create` / `Update` schemas. The upgrade is purely at the boundary; the model side stays `Mapped[str]`.
- `Blueprint.email()` is removed; the migration call is `t.string("email", 254).unique()`.

The general-purpose improvements that were uncovered while implementing Option B — `PydanticType.load_dialect_impl` returning `JSONB` on PostgreSQL — are kept. They benefit every future `PydanticType` column (e.g. settings, preferences) and have no email-specific coupling.

## Rationale

### Why Option A wins

1. **It serves the actual need.** "Email must be a valid email address" is a boundary-validation concern. The API receives strings from clients; `EmailStr` rejects malformed ones before they reach the model. Once stored, the value is a `str` because that's what every consumer wants — for templating, logging, comparison, indexing, and SQL projection.
2. **Storage stays conventional.** `VARCHAR(254)` is what every operator expects when they `SELECT email FROM users WHERE …`. Reports, admin tools, BI pipelines, and ad-hoc psql sessions don't need to know about JSON path expressions or value-object payloads.
3. **Indexing is free.** `UNIQUE` implies a B-tree unique index on every supported dialect. No `JSONB` operator-class trickery, no functional indexes on `email->>'value'` for case-insensitive lookups, no per-dialect quirks.
4. **`make:schema` closes the validation gap.** Without the name-based heuristic the user would have to remember to hand-edit every generated schema to swap `str` for `EmailStr`. The heuristic catches the common case (`email`, `billing_email`, `contact_email`) automatically; opt-out is editing the generated file, which is explicitly marked as user-editable.
5. **One concept, one place.** Validation rules live in the boundary schema. Persistence is dumb storage. The split is the same one the framework uses everywhere else (ADR-011 + the `PydanticType` doctrine).

### Why Option B lost — even after we made it work

1. **Single use case doesn't justify a framework abstraction.** Rule of Three (`100-coding-standards.mdc`): a value-object column for *one* type is duplication of mechanism, not abstraction of behavior. There's no `Money`, `IpAddress`, `PhoneNumber`, or `Url` column today. Bring the value-object machinery back when there is.
2. **Dialect leakage.** The Postgres `json` → `jsonb` requirement, the SQLite-vs-Postgres-vs-MySQL UNIQUE semantics on JSON, and the `where_raw` coercion gap — all real, all documentable, none zero-cost. A `VARCHAR` column has none of these.
3. **In-memory caveat.** `User.create(email="x@y.com")` leaves `user.email` as a `str` until reload, because SQLA doesn't route bind values back through `process_result_value`. The `@validates` workaround is correct but is workaround-shaped — one more thing every adopter must remember.
4. **Operational opacity.** `email = '{"value": "alice@example.com"}'` in a database is harder to grep, harder to dump, harder to import from CSV. The shape is correct *for the ORM* and wrong *for everyone else who touches the data*.
5. **The value object had no unique behavior.** `EmailAddress.__eq__("alice@example.com")`, `__str__`, `__hash__` — every method delegated to the inner `str`. The only thing the value object did that a `str` doesn't is validation, and Pydantic does that perfectly fine at the boundary.

### Why not Option C

A `VARCHAR`-backed `TypeDecorator` that converts `str ↔ EmailAddress` was considered. It preserves the on-disk simplicity of Option A and adds typed attribute reads. But:

- It re-introduces `EmailAddress` and its full API surface — `@validates` recipes, `to_dict()` shape, kwarg-shorthand semantics — for a value object that exists only because the column was clever. That's the value-object cost of Option B without the JSON storage cost.
- `Mapped[str]` reads exactly as well as `Mapped[EmailAddress]` once the boundary validation is in place. Nobody reads `user.email` and wishes it had domain methods that don't exist.

Defer C until at least two real value-object columns exist.

## Consequences

### Positive

- Smaller framework surface: `arvel.database` exports two fewer symbols (`email`, `EmailAddress`). The schema DSL drops one method (`Blueprint.email`).
- No dialect-awareness burden on the email path. The cross-dialect test matrix for emails is exactly the matrix the `string()` helper already covers.
- The example app is conventional. New contributors recognize `email: Mapped[str] = string(254, unique=True)` immediately.
- `make:schema` now does meaningful work on email columns automatically — the validation gap is closed without any user action.

### Negative

- Users who *want* domain methods on email (case-insensitive comparison, `.domain` / `.local_part`) must hand-roll a `TypeDecorator` or wrap in a property. The framework no longer provides one. This is intentional — see Rationale §B.1.
- The `@validates` recipe is no longer needed and was deleted from `eloquent.md`. Users coming from the old docs will not find it.

### Migration / cleanup

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

## Alternatives considered

| Option | Why not |
|---|---|
| Option B (JSON value object) | Five real costs (storage opacity, dialect leakage, in-memory caveat, single use case, value object has no unique behavior) outweigh the one benefit (typed attribute reads as `EmailAddress`). |
| Option C (VARCHAR + value-object cast) | Defers all of Option B's value-object costs without the JSON storage cost — but only earns its place when at least two value-object columns exist. Rule of Three. |
| SQLModel | Rejected wholesale in ADR-076 / research 002 — Pyright unsupported, PEP 649 breakage, metaclass fusion. Not specific to email. |
| `@validates` on the column | Server-side; only catches Python-set values, not raw `UPDATE` statements. Boundary validation catches both because client traffic always goes through Pydantic. |

## Notes

The `make:schema` email-detection heuristic is intentionally name-based, not type-annotation-based. It runs at codegen time against SQLA column metadata, where the only signal available is the column name and type. The alternative — a model-level `__email_columns__ = ["email", "billing_email"]` declaration — was rejected as redundant ceremony; column names are already the source of truth.

The 2026-05-20 cross-dialect test matrix (Postgres + MySQL + SQLite via Testcontainers) that was added for Option B is removed along with the test file. The pattern stays in the repo for future use — see `tests/cache/stores/test_database_store_sql_integration.py` for the canonical shape.
