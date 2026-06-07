# SAD-001 — Framework-level local file serving

**Work Item**: WI-arvel-001 | **PRD**: `docs/prd/PRD-001-local-storage-serving.md`
**Related ADRs**: ADR-009 § 4 (amended — HMAC temp URLs + route in `register()`)

---

## Overview

Make the framework serve the URLs the `local` driver already mints, the way Laravel's
`'serve' => true` does. No new subsystem — three small, surgical changes plus a config field.

## Components touched

| Component | Change |
|---|---|
| `config/storage_config.py` → `LocalConfig` | Add `serve: bool = True` (`STORAGE_LOCAL_SERVE`) |
| `storage/manager.py` → `StorageManager` | Already accepts `app_key`; no change needed there |
| `providers/storage_provider.py` → `StorageServiceProvider` | Pass `APP_KEY` to the manager; register the serve route in `register()` |
| `kits/arvel-ecommerce-kit` | Drop custom `/media` route; set `STORAGE_LOCAL_URL` |

## Serve route

Registered in `StorageServiceProvider.register()` (not `boot()` — see ADR-009 § 4 amendment) via the
`Route` facade, mirroring `AuthServiceProvider._mount_routes`:

```
GET {STORAGE_LOCAL_URL}/{path:path}   name="storage.local"   include_in_schema=False
```

Registration guard — all three must hold:
1. default driver is `local`
2. `STORAGE_LOCAL_SERVE` is on
3. `STORAGE_LOCAL_URL` is relative (starts with `/`)

### Handler flow

```
if token and expires present:
    if signer is None or not signer.verify(path, token, expires):  -> 403
contents = LocalDriver.get(path)            # _safe_path guards traversal
except FileNotFoundError | StoragePathError -> 404
return 200, body, Content-Type=guess, Cache-Control
```

- Public files (no signature) serve directly.
- Signed URLs (from `temporary_url()`) are verified; tampered/expired → 403.
- Traversal/missing → 404 (NFR-3: no info leak).

## APP_KEY wiring (story 3)

`StorageServiceProvider.register()` reads `APP_KEY` from the environment (same source as the
`Crypt` facade) and passes it to `StorageManager(app_key=...)`. The manager already forwards it to
`LocalDriver`, which builds a `TemporaryUrlSigner`. The serve route reuses the same signer to
verify — closing the round-trip in FR-6.

## Threat model (STRIDE, abridged — Tier 3)

| Threat | Vector | Mitigation |
|---|---|---|
| Tampering | Path traversal to read arbitrary files | `LocalDriver._safe_path` (existing, tested); handler returns 404 on `StoragePathError` |
| Spoofing | Forged signed URL | HMAC-SHA256 over `path:expires`, key via HKDF from `APP_KEY`; `compare_digest` |
| Elevation | Reusing an expired link | `expires` is part of the HMAC message and checked against wall clock |
| Info disclosure | Stack trace / path echo on error | Generic 403/404, no body detail |

## Out of scope (deferred)

Named disks (story 1), visibility (story 5), cloud signed URLs (story 7), doc drift (story 8).
Without visibility, the route serves any file under the root when requested without a signature;
this matches Laravel `serve` for public disks and is documented as a known limitation.
