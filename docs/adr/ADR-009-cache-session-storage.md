# ADR-009 — Cache, Session & Storage

**Status**: Accepted
**Date**: original decisions 2026-05-17 – 2026-05-24; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: Protocol-based store interfaces, lazy optional-dep imports, opt-in session middleware, local-driver temp URL HMAC, cache versioner invalidation, path-generator DI resolution, queue restart marker.

## Why this is one ADR

Cache, session, and filesystem stores share one core idea: protocol-shaped backends with lazy imports and a small set of cross-cutting helpers (HMAC URLs, versioner, restart marker). One ADR captures all seven decisions.

---

## § 1 — Store/Driver interfaces as `typing.Protocol`, not ABC

**Originally**: ADR-077 · Date: 2026-05-17

### Context

WI-006 introduces `CacheStore`, `SessionStore`, and `StorageDisk` as the interface contract for
all store/driver implementations. The choice is between `ABC` (abstract base class) and
`typing.Protocol`.

### Decision

All three interfaces are `typing.Protocol` (structural subtyping), not `ABC` (nominal subtyping).

### Rationale

1. **Third-party extensibility**: a third-party cache store doesn't need to `import arvel` to
   implement the protocol. Duck typing works at runtime; the type checker verifies compliance.
2. **Test isolation**: test stores (e.g., `SpyStore`) can be defined in a test file with no
   framework import, keeping the test boundary clean.
3. **`runtime_checkable`**: `isinstance(store, CacheStore)` works for the `TaggedCache` assertion.
4. **Consistency**: `HttpExceptionHandler` (WI-002) and `RateLimiterStore` (WI-002) both used
   `Protocol`-style contracts. This is the established Arvel pattern.

### Consequences

- Store implementations do NOT inherit from `CacheStore` / `SessionStore` / `StorageDisk`.
  They implement the methods with matching signatures.
- Type checkers verify protocol compliance at call sites (e.g., `CacheManager.store()` return type).
- Adding a required method to the protocol is a breaking change for all existing stores.

---

## § 2 — Lazy optional-dependency imports in cloud drivers

**Originally**: ADR-078 · Date: 2026-05-17

### Context

`S3Driver`, `GcsDriver`, and `AzureDriver` require `aioboto3`, `google-cloud-storage`, and
`azure-storage-blob` respectively. These are heavy packages. Apps that only use local storage
should not be forced to install them.

The question is: where does the import happen?

### Decision

Cloud driver packages are imported inside `__init__` (not at module level). The import is
wrapped in `try/except ImportError` with a friendly re-raise.

```python
class S3Driver:
    def __init__(self, config: S3Config) -> None:
        try:
            import aioboto3  # noqa: PLC0415
            self._aioboto3 = aioboto3
        except ImportError:
            raise ImportError(
                "S3Driver requires 'arvel[s3]'. "
                "Install with: pip install \"arvel[s3]\""
            ) from None
```

### Rationale

1. **Import safety**: `from arvel.storage import LocalDriver` works with zero extras installed.
2. **Error at use, not at startup**: the error surfaces when the driver is instantiated (i.e.,
   when the developer explicitly asks for it), not during application boot.
3. **Pyright compliance**: `self._aioboto3 = aioboto3` stores the module reference; subsequent
   attribute accesses go through `self._aioboto3`, which pyright treats as `ModuleType`.
   Where necessary, `# pyright: ignore[reportUnknownMemberType]` is used on specific accesses
   since aioboto3 has no type stubs (consistent with WI-005 `shell.py` precedent).
4. **`noqa: PLC0415`**: Ruff's "import not at top of file" rule is suppressed inline at the
   import site. This is the single approved exception for optional-dep guards.

### Consequences

- Apps that miss an extra get a clear, actionable error at driver instantiation.
- The CI extras-matrix job (DX gate 49) verifies each extra installs and imports correctly.
- Every cloud driver `__init__` has a `# pyright: ignore[reportMissingModuleSource]` for the
  `import aioboto3` line (no stubs for optional deps).

---

## § 3 — StartSession middleware is opt-in, not auto-global

**Originally**: ADR-079 · Date: 2026-05-17

### Context

`SessionServiceProvider` could automatically prepend `StartSession` to every request's middleware
stack, or it could register the middleware under a name and let each app opt in.

### Decision

`StartSession` is NOT auto-applied globally. `SessionServiceProvider.register()` binds the
`StartSession` class under the name `"session"` in the middleware registry.

Apps enable it per group:

```python
Application.configure(...)
    .with_middleware(lambda mw: mw.group("web", ["session", "csrf"]))
```

### Rationale

1. **API-only apps**: apps that build pure JSON APIs (no browser, no cookies) should not pay the
   session read/write overhead on every request. Auto-global would force them to disable it
   explicitly — the wrong default.
2. **Laravel parity**: Laravel's `StartSession` middleware is in the `web` group, not `global`.
   Apps must explicitly add routes to the `web` group. Arvel mirrors this.
3. **Performance**: session read/write is I/O. Opt-in keeps the critical path (API routes) lean.
4. **Consistency with throttle**: `Throttle` middleware (WI-002) is also opt-in via group.

### Consequences

- Apps that forget to add `"session"` to their middleware group will find `request.state.session`
  absent. The error message from accessing it should be clear: "Session not started — add the
  'session' middleware to your route group."
- The skeleton's `routes/web.py` will include a comment showing how to enable sessions.

---

## § 4 — LocalDriver temporary URLs use HMAC-SHA256 + expiry

**Originally**: ADR-080 · Date: 2026-05-17

### Context

`S3Driver`, `GcsDriver`, and `AzureDriver` have native pre-signed URL mechanisms in their SDKs.
`LocalDriver` has no equivalent — it serves files from the local filesystem. WI-006 requires all
`StorageDisk` implementations to support `temporary_url(path, ttl)`.

### Decision

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

### Rationale

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
> `storage:link` (see ADR-022). The route here (at `STORAGE_LOCAL_URL`) streams through the app and
> supports signed temp URLs; the static mount bypasses the app for plain public assets. They
> coexist on distinct paths unless `STORAGE_LOCAL_URL` is also `/storage`.

### Consequences

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

---

## § 5 — `CacheVersioner` — Version-stamp invalidation without flush

**Originally**: ADR-081 · Date: 2026-05-24

### Context

The e-commerce demo's `ItemService` and the fullstack Vue demo needed a pattern to
invalidate list caches without calling `Cache.flush()`, which would evict rate-limit
counters, session data, and unrelated cached entries from the same store.

### Decision

Ship `CacheVersioner` in `arvel.cache.versioner` with the following contract:

```python
versioner = CacheVersioner("items:list", store=cache_store)
key = await versioner.versioned_key("user:1", "page:2")   # unique per version
await versioner.invalidate()                               # bumps version counter
```

`versioned_key(*parts)` returns `{namespace}:{parts_hash}:v{version}`. When `invalidate()`
increments the version counter, all old keys become unreachable — they expire via TTL
without an explicit delete. `Cache.flush()` is never called.

Version counters are stored under namespaced keys to prevent collisions:
`__arvel_versioner__:{namespace}:v`.

### Rationale

- **No flush**: `Cache.flush()` clears the entire store — not acceptable in shared-store
  deployments where rate-limiters and sessions live alongside list caches.
- **Namespace isolation**: Without namespacing, two `CacheVersioner` instances for
  different resource types could collide on version counter keys.
- **TTL-based GC**: Old versioned keys expire naturally — no background cleanup job needed.
- **`arvel.cache` placement**: Cache utilities belong in the cache module. No cross-module
  imports.

### Rejected Alternatives

- `Cache.delete()` on every list key: requires tracking which keys exist — error-prone
  under concurrent writes and across multiple app instances.
- `Cache.tags()` (if supported): not all cache drivers support tag-based invalidation;
  `CacheVersioner` works on any driver.

---

## § 6 — PathGenerator resolved via DI container with fallback

**Originally**: ADR-082 · Date: 2026-05-24

### Context

`DefaultPathGenerator` is currently hard-coded throughout `arvel-image`. Consumers expect to
bind a custom `PathGenerator` in their service provider and have the runtime pick it up. Our
implementation ignores custom bindings, making `PathGenerator` customisation silently
ineffective.

### Decision

Introduce a single `_resolve_path_generator()` helper:

```python
def _resolve_path_generator() -> PathGenerator:
    from arvel.container import app
    return app.make(PathGenerator, default=DefaultPathGenerator())
```

All call sites that previously wrote `DefaultPathGenerator()` call this helper instead.

### Consequences

- Developers can bind a custom `PathGenerator` in any `ServiceProvider` and it will be used.
- If the container is not initialised (unit-test context without app bootstrap), the fallback
  `DefaultPathGenerator()` is used — existing tests pass without change.
- `app.make` is a lightweight dict lookup; no measurable overhead.

---

## § 7 — Queue restart marker via cache

**Originally**: ADR-083 · Date: 2026-05-19

### Context

`queue:restart` needs to signal all running workers to exit gracefully so the next supervisor (systemd, supervisord, k8s) restarts them with the latest code. The signal must:

- Reach workers running in separate processes.
- Be cheap to poll (workers check it every loop iteration).
- Be cleared automatically when workers restart.

Laravel uses a Redis/cache key (`illuminate:queue:restart`) with a timestamp. Workers compare it to their own `started_at`.

### Decision

Use a **cache-key marker** at `arvel:queue:restart` holding the most recent restart timestamp (ISO 8601 UTC). Workers compare the marker against their own `started_at` once per loop iteration; if the marker is newer, they exit.

### Rationale

| Aspect | Cache key | File marker | Signal (SIGUSR1) |
|---|---|---|---|
| Cross-process | ✓ | ✓ | ✗ (needs PID list) |
| Per-worker scope | ✓ (timestamp comparison) | ✗ (no per-worker state) | ✓ |
| Survives DB outage | ✓ | ✓ | ✓ |
| Cheap to poll | ✓ (cache get) | ✓ (stat) | ✓ (no poll needed) |
| Multi-host | ✓ (shared Redis) | ✗ | ✗ |
| Auto-clears | timestamp-based | manual cleanup | event-based |

**Cache wins** because:

1. Queue workers already require a cache binding (rate-limit store, idempotency).
2. The timestamp comparison is idempotent — workers started after the marker simply ignore it. No cleanup logic needed.
3. Multi-host queue clusters can share a cache key without each worker needing local-filesystem coordination.

### Consequences

#### Positive

- Workers respond within one loop iteration (~1 second worst case).
- Same mechanism works in multi-host deployments.
- Idempotent: a stale marker doesn't trigger repeated restarts; workers compare against their own start time.

#### Negative

- Requires a cache binding (acceptable — already required for other queue features).
- Marker persists indefinitely. This is fine: comparison is against `started_at`, so it never causes ghost-restarts.

### Alternatives rejected

- **File marker**: doesn't work cross-host in clustered queues.
- **SIGUSR1 signal**: requires the CLI to know every worker's PID. Workers in containers or supervisor-managed environments don't expose their PIDs in a discoverable way.
- **REST API / RPC**: introduces a new endpoint and authentication concern for an internal-only signal.

### Implementation notes

- Cache key: `arvel:queue:restart` (literal string; per-project prefix not needed).
- Value: ISO 8601 timestamp in UTC.
- Owner: `arvel.queue.restart.QueueRestartSignal`.
- Polled by: `Worker.run_until()` once per iteration.
- Comparison: `marker_timestamp > worker.started_at` → set stop event and exit.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-077 | 2026-05-17 | Store/Driver interfaces as `typing.Protocol`, not ABC | § 1 |
| ADR-078 | 2026-05-17 | Lazy optional-dependency imports in cloud drivers | § 2 |
| ADR-079 | 2026-05-17 | StartSession middleware is opt-in, not auto-global | § 3 |
| ADR-080 | 2026-05-17 | LocalDriver temporary URLs use HMAC-SHA256 + expiry | § 4 |
| ADR-081 | 2026-05-24 | `CacheVersioner` — Version-stamp invalidation without flush | § 5 |
| ADR-082 | 2026-05-24 | PathGenerator resolved via DI container with fallback | § 6 |
| ADR-083 | 2026-05-19 | Queue restart marker via cache | § 7 |
