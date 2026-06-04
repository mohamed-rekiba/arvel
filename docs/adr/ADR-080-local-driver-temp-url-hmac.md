# ADR-080 — LocalDriver temporary URLs use HMAC-SHA256 + expiry

**Status**: Accepted
**Date**: 2026-05-17
**Deciders**: Arvel core team

---

## Context

`S3Driver`, `GcsDriver`, and `AzureDriver` have native pre-signed URL mechanisms in their SDKs.
`LocalDriver` has no equivalent — it serves files from the local filesystem. WI-006 requires all
`StorageDisk` implementations to support `temporary_url(path, ttl)`.

## Decision

`LocalDriver.temporary_url()` issues HMAC-SHA256-signed URLs:

```
{base_url}/storage/{path}?token={b64url(hmac)}&expires={unix_ts}
```

`StorageServiceProvider.register()` registers `GET {STORAGE_LOCAL_URL}/{path:path}` on the
application's `Router`. The handler:
1. If `token` and `expires` query params are present, recomputes the HMAC, compares with
   `hmac.compare_digest` (constant-time), and checks `int(expires) > int(time.time())`. Invalid,
   tampered, or expired → `HTTP 403`.
2. If no signature params are present, the file is treated as public and served directly.
3. Serves the file via `LocalDriver.get()`; missing file or path-traversal attempt → `HTTP 404`
   (never `500`, never a read outside the root).

The HMAC key is derived from `APP_KEY` using HKDF-SHA256 (info `b"arvel-storage-tmp-url"`, per
`TemporaryUrlSigner`).

> **Amendment (WI-arvel-001).** The original draft said the route is registered in
> `StorageServiceProvider.boot()`. That is wrong: `Router.register_with_app()` runs synchronously
> during `create_asgi()` — *before* the async `boot()` pass — so a route added in `boot()` is
> invisible to FastAPI. Routes are registered in `register()`, matching `AuthServiceProvider`.
>
> The original draft also described the handler as signature-only (always `403` without a valid
> token). That conflicts with Laravel's `serve => true`, which serves public files directly and
> only validates a signature when the URL carries one. The handler now serves public files and
> enforces signatures when present. Per-file visibility (rejecting a private file requested without
> a signature) is deferred to backlog story 5.

## Rationale

1. **No native pre-sign**: local disk has no equivalent of S3 SigV4. HMAC is the standard
   approach for stateless signed tokens.
2. **HMAC-SHA256**: secure, fast, constant-time comparison available via stdlib `hmac.compare_digest`.
3. **Separate key derivation**: using HKDF with a distinct info string isolates the storage signing
   key from the session encryption key even if both derive from `APP_KEY`.
4. **No MD5/SHA1**: Article IV §2 forbids rolling our own crypto; HMAC-SHA256 is the minimum
   acceptable MAC per OWASP A04.
5. **Expiry in plaintext**: the expiry is in the URL (not inside the HMAC input — it IS part of the
   HMAC message). An attacker cannot extend expiry without invalidating the token.

> **Amendment (WI-arvel-003).** This route is one of two local-serving modes. The other is a
> static `StaticFiles` mount at `/storage` serving the `public/storage` symlink created by
> `storage:link` (see ADR-134). The route here (at `STORAGE_LOCAL_URL`) streams through the app and
> supports signed temp URLs; the static mount bypasses the app for plain public assets. They
> coexist on distinct paths unless `STORAGE_LOCAL_URL` is also `/storage`.

## Consequences

- `temporary_url()` requires `APP_KEY`. The serve route's *public* path does not — public files
  serve without a key. If `APP_KEY` is absent, signed URLs raise at generation time
  (`LocalDriver.temporary_url`) and the route simply has no signatures to verify.
- The serve route is only registered when (a) the default driver is `local`, (b)
  `STORAGE_LOCAL_SERVE` is on, and (c) `STORAGE_LOCAL_URL` is a relative path (`/…`). An absolute
  URL means a CDN/object store serves the files, so no route is registered. Apps using only cloud
  drivers don't get this route.
- File serving is synchronous only in the sense that the route handler awaits `LocalDriver.get()`
  — it uses `anyio.open_file` internally.
- Token length: HMAC-SHA256 = 32 bytes → 43 chars Base64url. URL overhead is ~80 chars total.
