# ADR-004 — Two PyPI packages at 0.x; defer sub-splitting; use optional extras for drivers

**Date**: 2026-05-17
**Status**: Accepted
**Deciders**: Solution Architect (autonomous)
**Scope**: PyPI distribution surface

---

## Context

Laravel ships ~30 first-party packages: `illuminate/database`, `illuminate/queue`, `illuminate/mail`, etc. Each can be installed independently. The constellation is held together by Composer's metadata graph.

For Python, the equivalent question is: do we ship `arvel-container`, `arvel-orm`, `arvel-queue`, `arvel-mail`, …? Or one `arvel` with optional extras?

## Options considered

### Option A — One package per subsystem (Laravel pattern)

**Pros**: Users only install what they use; smaller dependency footprint per app.
**Cons**:
- 30+ packages to release in lock-step → release engineering nightmare.
- Cross-package imports are awkward in Python (no Composer-equivalent metadata graph).
- Type stubs and circular-dep avoidance get harder.
- Discoverability suffers — "where is `Mailable`?" requires `arvel-mail`, not obvious.
- At 0.x with rapid breaking changes, this multiplies coordination cost.

### Option B — Single `arvel` package with optional extras (chosen at 0.x)

**Pros**:
- `pip install arvel[redis,postgres,queue]` is the same UX as Laravel — only install drivers you need.
- Core code lives together; one import path; one `__all__`.
- One release artifact; one CHANGELOG; one upgrade guide.
- Easy refactor — moving code between subsystems doesn't break user installs.

**Cons**:
- A user installing `arvel` gets *all* the optional-imports paths in their site-packages tree even if they don't use them (small disk cost; not a runtime cost since we lazy-import driver modules).
- We have to be disciplined about optional-extras boundaries (mitigated by import-error tests).

### Option C — Hybrid: split major subsystems after 1.0 if real demand emerges

**Pros**: Best of both — start simple, split when you have evidence; allows community to fork sub-packages.
**Cons**: Requires careful API design now so we *could* split later.

## Decision

**Option B at 0.x, Option C considered post-1.0.**

Concretely, during 0.x we ship two packages:

1. `arvel` — the framework
2. `arvel-cli` — the global CLI for `arvel new myapp`

Optional extras on `arvel`:
- `arvel[postgres]` → `asyncpg`, `psycopg[binary]`
- `arvel[mysql]` → `aiomysql`, `pymysql`
- `arvel[sqlite]` → `aiosqlite`
- `arvel[redis]` → `redis[hiredis]`
- `arvel[queue]` → `taskiq[redis]`
- `arvel[mail-ses]` → `aioboto3` (post-Phase 8)
- `arvel[mail-resend]` → driver SDK (post-Phase 8)
- `arvel[storage-s3]` → `aioboto3` (post-Phase 5)
- `arvel[storage-gcs]` → `gcloud-aio-storage` (post-Phase 5)
- `arvel[storage-azure]` → `azure-storage-blob` (post-Phase 5)
- `arvel[broadcasting]` → `websockets` (post-Phase 9)
- `arvel[auth-jwt]` → `pyjwt[crypto]` (post-Phase 6)
- `arvel[auth-oauth]` → `authlib` (post-Phase 6)

Post-1.0, if a subsystem outgrows the extras pattern (e.g., the broadcasting WS server becomes its own daemon), we may split it into a sibling package then.

## Consequences

- Driver modules must be lazy-imported with a clear `ImportError` ("install `arvel[redis]` to use Redis cache").
- Each optional extra has its own driver-availability test in CI (the test is skipped if the extra isn't installed; CI installs all extras).
- `arvel-cli` stays tiny — just clones the skeleton + replaces template tokens. No runtime dep on `arvel`.

## References

- Laravel's package boundaries: https://github.com/illuminate/
- Django's "extras_require" pattern.
- pip extras_require: https://packaging.python.org/en/latest/specifications/dependency-specifiers/#extras
