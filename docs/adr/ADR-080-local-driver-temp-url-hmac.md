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

`StorageServiceProvider.boot()` registers `GET /storage/{path:path}` on the application's
`Router`. The handler:
1. Parses `expires` and `token`.
2. Recomputes HMAC and compares with `hmac.compare_digest` (constant-time).
3. Checks `int(expires) > int(time.time())`.
4. If valid: streams the file via `LocalDriver.get()`.
5. Otherwise: returns `HTTP 403`.

The HMAC key is derived from `APP_KEY` using HKDF-SHA256 with info `b"arvel.storage.temp_url"`.

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

## Consequences

- `LocalDriver` requires `APP_KEY` to be set. If absent, `StorageServiceProvider.boot()` raises
  `ConfigError`.
- The `/storage/{path:path}` route is only registered when `LocalDriver` is the configured disk.
  Apps using only cloud drivers don't get this route.
- File serving is synchronous only in the sense that the route handler awaits `LocalDriver.get()`
  — it uses `anyio.open_file` internally.
- Token length: HMAC-SHA256 = 32 bytes → 43 chars Base64url. URL overhead is ~80 chars total.
