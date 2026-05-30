# ADR-016 — Sanctioned http→database exemption for `DatabaseTransaction` middleware

**Status**: Accepted
**Date**: 2026-05-17

## Context

The ORM ships a request-scoped transaction middleware so handlers get
automatic commit-on-2xx / rollback-on-exception semantics. The natural place
for this middleware is `arvel.http.middleware.database_transaction`, because
it's an HTTP middleware. But the forbidden-import rule
(`tests/architecture/test_layering.py`) prohibits `arvel.http.*` from
importing `arvel.database.*` symbols.

Three options:

| Option | Pros | Cons |
|---|---|---|
| A. Ship the middleware in `arvel.database.middleware` instead | No exemption needed | Hides an HTTP-layer concept from where developers expect it; `arvel.database.*` then has to know about Starlette `BaseHTTPMiddleware` (a different layering violation) |
| B. Resolve the session via `Application.container.amake(AsyncSession)` inside the middleware, importing only `arvel.container` types | No direct database import | The middleware still depends on `AsyncSession` being a SQLA type; renaming the type is felt across the http boundary |
| C. **Named exemption — explicitly allow `arvel.http.middleware.database_transaction` to import `arvel.database`** | Honest: the dependency is real and intentional | One hand-maintained allowlist entry |

## Decision

Option C. The forbidden-import test maintains a short allowlist with comments:

```python
# tests/architecture/test_layering.py
ALLOWED_HTTP_TO_DATABASE_IMPORTS = {
    # The DatabaseTransaction middleware bridges HTTP request lifecycle to
    # ORM session lifecycle. This is a sanctioned exception (ADR-016) — it
    # exists because the middleware is conceptually HTTP-flavoured (responds
    # to request/response events) but operates on an ORM primitive.
    "arvel.http.middleware.database_transaction": {
        "arvel.database",
        "sqlalchemy.ext.asyncio",
    },
}
```

Every other `arvel.http.*` module is forbidden from importing `arvel.database.*`.
Every `arvel.database.*` module is forbidden from importing `arvel.http.*`
(no exemption in that direction — the database layer must not know about HTTP).

## Consequences

**Positive**:
- The middleware lives where developers expect it (HTTP middleware in
  `arvel.http.middleware`).
- The exemption is one named entry with a comment, easy to audit.
- The forbidden-import test is the canonical source of truth — adding a
  second exemption requires editing the same file and writing a justification.

**Negative**:
- Future contributors might try to expand the exemption casually. We mitigate
  via code review: any new entry in `ALLOWED_HTTP_TO_DATABASE_IMPORTS`
  requires an ADR (or extension of this one).

**Enforcement**:
- The forbidden-import test asserts: every `arvel.http.*` module not in
  `ALLOWED_HTTP_TO_DATABASE_IMPORTS` must not import `arvel.database.*`.
- New entries to the allowlist require an ADR.
