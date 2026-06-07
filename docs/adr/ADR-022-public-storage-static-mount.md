# ADR-022 — Serve `public/storage` via a scoped StaticFiles mount

**Status**: Accepted
**Date**: 2026-06-03 (renumbered from ADR-137 in WI-arvel-003 on 2026-06-05)
**Last reconciled**: 2026-06-07 (WI-arvel-005 renumbered ADR-134 → ADR-022)
**Deciders**: Arvel core team (autonomous, original WI was WI-arvel-003-storage-link)
**Related**: ADR-009 § 4 (LocalDriver serve=true route)

> Renumbered from ADR-137 in WI-arvel-003 (2026-06-05) to close the gap left by
> merging the seven arvel-image ADRs into a single ADR-020.

---

## Context

`arvel storage:link` symlinks `public/storage → storage/app/public`, mirroring Laravel. But Arvel runs under ASGI (uvicorn), and nothing serves the `public/` tree — it only holds `public/asgi.py`. So the symlink is inert: linked files aren't retrievable without a hand-configured reverse proxy. Laravel's public-disk model works because `public/` is the web server's document root; Arvel has no such static webroot by default.

## Decision

`Application.into_asgi()` mounts a Starlette `StaticFiles` instance at `/storage`, serving the `public/storage` directory:

```python
storage_dir = self.base_path() / "public" / "storage"
if storage_dir.exists():
    fa.mount("/storage", StaticFiles(directory=storage_dir), name="storage.public")
```

- **Scoped to `public/storage`** (not the parent `public/`): mounting the parent would serve `asgi.py` as source (OWASP A05) and make `Mount("/")` swallow framework JSON 404s for unmatched routes. The `/storage` mount only claims `/storage/*`.
- **Mounted only when the link exists at boot.** Starlette's `StaticFiles` re-checks the directory on the first request (even with `check_dir=False`) and raises if it's missing — so a "lazy" mount would 500 instead of 404. Gating on `storage_dir.exists()` (which follows the symlink, treating a dangling link as absent) means: no link → no mount → the path 404s through the framework. Run `storage:link`, then (re)start the server.
- **Resolved against the app base path**, not CWD, so it's correct under tests and non-root working directories.

Starlette's realpath/commonpath containment serves the symlinked files correctly: the mounted directory *is* the symlink, so its realpath (`storage/app/public`) legitimately contains the files. Path traversal outside that realpath is rejected with 404.

## Alternatives considered

1. **Mount the full `public/` webroot** (Laravel-faithful) — rejected: serves `asgi.py` source and shadows API 404s.
2. **Custom ASGI middleware with `.py`/dotfile blocking + lexical containment** — rejected as over-engineered once scope narrowed to `public/storage`, which has no source files.
3. **Drop `storage:link` entirely** — rejected: it's the standard "offload to a static server / reverse proxy" path; keeping it (now functional) preserves Laravel parity.

## Consequences

- After `storage:link`, files serve at `/storage/*` with no reverse proxy.
- Two coexisting local-serving modes: the `serve=true` app route (ADR-009 § 4, at `STORAGE_LOCAL_URL`, signed temp URLs) and this static mount (at `/storage`). They collide only if `STORAGE_LOCAL_URL` is also `/storage`. To point `Storage.url()` at the static path, set `STORAGE_LOCAL_URL=/storage`.
- Static assets serve even under maintenance mode (mount is outside the maintenance middleware). Acceptable for public assets.
- High-traffic deployments should still front with nginx/CDN; the mount is the zero-config default, not a performance ceiling.
