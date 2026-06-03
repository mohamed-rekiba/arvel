# Design — Static serving for `storage:link`

**WI**: WI-arvel-003
**Date**: 2026-06-03
**Author**: Product Engineer (autonomous)

## Problem

`arvel storage:link` symlinks `public/storage → storage/app/public`, mirroring Laravel. But Arvel is ASGI-first: nothing serves the `public/` tree (it only holds `public/asgi.py`). So the symlink is inert under uvicorn — files aren't retrievable unless the operator hand-configures a reverse proxy. The command exists but does nothing on its own.

## Goal

Make `storage:link` self-sufficient: after running it, files are retrievable at `/storage/*` with no reverse proxy, matching Laravel's public-disk behavior.

## Approach (decided)

Mount `public/storage` as static files at `/storage` in `Application.into_asgi()`:

```python
storage_dir = self.base_path() / "public" / "storage"
if storage_dir.exists():
    fa.mount("/storage", StaticFiles(directory=storage_dir), name="storage.public")
```

Key decisions and why:

- **Scope to `public/storage`, not `public/`.** Mounting the parent `public/` would (a) risk serving `asgi.py` as source (OWASP A05) and (b) turn `Mount("/")` into the terminal handler for unmatched paths, breaking API JSON 404s. Scoping to `/storage` avoids both — it only claims `/storage/*`.
- **Plain `StaticFiles`, no custom middleware.** When the mounted directory *is* the symlink (`public/storage → storage/app/public`), Starlette resolves the directory's realpath and the files genuinely live under it, so the realpath/containment check passes. The escape problem only existed when mounting the parent.
- **Mount only when the link exists at boot.** `StaticFiles` re-checks the directory on the first request and raises if missing (even with `check_dir=False`), so a lazy mount would 500. Gating on `storage_dir.exists()` means no link → no mount → framework 404. Run `storage:link`, then (re)start.
- **Resolve against the app base path**, not CWD — correct under tests and non-root working dirs.

## Relationship to the `serve=true` route

Two independent local-serving modes, both kept:

| Mode | Path | Mechanism | When |
|---|---|---|---|
| `serve=true` route (ADR-080) | `STORAGE_LOCAL_URL` | App streams via `disk.get()`, HMAC temp URLs | Default; works everywhere, no symlink |
| `storage:link` + static mount (this WI) | `/storage` | Starlette serves files from disk, bypassing app | Run the command; web-server-grade static serving |

They don't collide unless `STORAGE_LOCAL_URL` is also `/storage`. To make `Storage.url()` resolve to the static path, set `STORAGE_LOCAL_URL=/storage`.

## Out of scope

- Full `public/` webroot serving (rejected — source-disclosure + 404-shadowing).
- Changing disk roots or the `storage:link` symlink target.
- Multi-disk `serve` collision handling (Laravel issue #55356) — not triggered by this single-disk change.
