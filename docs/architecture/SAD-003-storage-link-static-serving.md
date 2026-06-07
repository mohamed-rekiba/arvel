# SAD-003 — Static serving for `storage:link`

**WI**: WI-arvel-003
**Status**: Accepted
**Related**: ADR-022 (this decision), ADR-009 § 4 (serve=true route)

## Overview

Add a Starlette `StaticFiles` mount at `/storage` serving the `public/storage` directory, so the `storage:link` symlink (`public/storage → storage/app/public`) makes files retrievable with no reverse proxy. Single component touched: `Application.into_asgi()`.

## Component touched

- `packages/arvel/src/arvel/application/application.py` — `into_asgi()` gains a guarded mount step (`_maybe_mount_public_storage`).

No new module is required; the implementation is a few lines using `starlette.staticfiles.StaticFiles`.

## Source flow

```
GET /storage/{path}
  → FastAPI route table (API routes, /docs, health — registered first, win)
  → Mount("/storage") → StaticFiles(directory="public/storage")
      → resolve realpath(public/storage) == storage/app/public
      → serve file if under that realpath, else 404
```

The mount is appended after `router.register_with_app(fa)` and the health route, so it only ever handles `/storage/*` that no earlier route claimed. It does not shadow other paths.

## Why not the parent `public/`

Mounting `public/` would (1) serve `public/asgi.py` as source (A05) and (2) make `Mount("/")` the terminal handler, converting framework JSON 404s into bare static 404s. Scoping to `public/storage` removes both, and Starlette's realpath containment serves the symlinked files correctly because the mounted directory *is* the symlink root.

## Threat model (STRIDE-lite)

| Threat | Vector | Mitigation |
|---|---|---|
| **Information disclosure** | Reading app source via `/storage/../asgi.py` | Starlette `StaticFiles` realpath/commonpath check rejects paths outside the resolved directory → 404. Mount is scoped to `public/storage`, never the parent. |
| **Information disclosure** | Serving `asgi.py`/`.env` | Those live in `public/` or repo root, not under `public/storage`; not reachable via this mount. |
| **Tampering** | Symlink repointed to a sensitive dir | Operator-controlled action (same trust as `storage:link`); no remote vector. |
| **DoS** | Large-file or many-file reads | Same exposure as any static server; deployments behind a proxy/CDN for high traffic (documented). Out of scope to rate-limit static assets. |

No auth, PII, or crypto surface → no Stage 4b. Security verified in QA-Post.

## Test coverage (planned)

Unit/feature: linked file served (200 + content-type), missing file 404, traversal rejected, boot-safe with no symlink, unrelated route unaffected. See `packages/arvel/tests/http/test_public_storage_mount.py`.
