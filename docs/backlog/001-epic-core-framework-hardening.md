# Epic 001: Core Framework Hardening

## Summary

Harden the arvel framework foundation by introducing a request-scoped `context/` module,
wiring observability into the default application lifecycle, establishing a `BaseService`
contract for service health and lifecycle management, fixing error handling to route through
the structured logging pipeline, and handling OS shutdown signals cleanly. Includes cache
lock enhancements and a lifecycle regression test suite to prevent future regressions.

---

## Stories

### Story 1: Request-scoped context module

**As a** framework user,
**I want** a `context/` module that holds per-request data (request_id, user_id, tenant_id, and arbitrary keys),
**so that** any code in the call stack can read or contribute context without receiving it as a function argument.

**Acceptance Criteria**:
- [ ] Given a request is in flight, when `Context.get("request_id")` is called from any module, then it returns the value set by `ContextMiddleware` at request start
- [ ] Given a request ends, when `ContextMiddleware` tears down, then all context keys are flushed and do not leak into the next request
- [ ] Given context is serialized for a queued job, when `Context.dehydrate()` is called, then all visible keys are returned as a dict; hidden keys are excluded
- [ ] Given a queue worker receives a job with context payload, when `Context.hydrate(data)` is called, then `Context.get()` returns the hydrated values
- [ ] Given `Context.add_hidden("db_password", ...)` is used, when `Context.all()` is called, then the hidden key is absent from the result
- [ ] Given `defer(fn)` is called during a request, when the response is sent, then `fn` is executed by `DeferredTaskMiddleware` before the ASGI scope closes
- [ ] Given a deferred function raises, when `DeferredTaskMiddleware` drains tasks, then the error is logged and remaining tasks still run
- [ ] Given `Concurrency.run([task1, task2])` is called, when one task raises, then the exception propagates without silencing others

**Security Requirements**:
- [ ] Hidden context keys must never appear in log output or `Context.all()` (protects tokens, internal IDs)
- [ ] `dehydrate()` must exclude hidden keys so they are not serialized into queue payloads

**Documentation Requirements**:
- [ ] Add `docs/site/docs/context.md` covering `Context`, `defer()`, and `Concurrency`

**Priority**: Must
**Complexity**: Medium
**Status**: Draft

---

### Story 2: Session-scoped log context binding

**As a** framework user,
**I want** every log line emitted during a request to automatically carry `request_id`, `user_id`, and `tenant_id`,
**so that** I can filter logs in OTel/Prometheus/Grafana to a single user session without adding context calls to every logger invocation.

**Acceptance Criteria**:
- [ ] Given `ObservabilityMiddleware` is mounted, when any `Log.info(...)` is called during a request, then the emitted log record contains `request_id` from the active `Context`
- [ ] Given a user has authenticated, when `Authenticate` middleware resolves the guard, then `Context.add("user_id", str(user.id))` is called before the handler runs
- [ ] Given a multi-tenant app sets `Context.add("tenant_id", tid)`, when any log is emitted in that request, then `tenant_id` appears in the log record
- [ ] Given no active request (e.g., a CLI command), when `Log.info(...)` is called, then `request_id` and `user_id` are absent from the record (no `None` keys)
- [ ] Given `LOG_REDACT_FIELDS` contains `"password"`, when a log record contains a `password` key, then the value is replaced with `***`

**Security Requirements**:
- [ ] `user_id` in logs must be the opaque ID (UUID/int), never the user's email or name
- [ ] Redaction must apply before the log record leaves the process (before OTel export)

**Documentation Requirements**:
- [ ] Update `docs/site/docs/logging.md` with session context binding example

**Priority**: Must
**Complexity**: Small
**Status**: Draft

---

### Story 3: Observability auto-wiring and startup logging

**As a** framework user,
**I want** `ObservabilityServiceProvider` registered by default and Uvicorn logs replaced by arvel's logging system,
**so that** I don't have to manually opt into observability on every new project and all logs are consistently structured.

**Acceptance Criteria**:
- [ ] Given an arvel app is created via `Application.configure(...).create()`, when `into_asgi()` is called, then `ObservabilityMiddleware` is mounted without any user configuration
- [ ] Given a uvicorn process starts, when the first request arrives, then no raw uvicorn `INFO:     GET /path HTTP/1.1 200` lines appear in stderr; access logs come from arvel's `Log` facade
- [ ] Given routes are registered via `Router`, when `Application.boot()` completes, then one structured log event per route is emitted at `DEBUG` level with `method`, `path`, and `name` fields
- [ ] Given `OTEL_EXPORTER_OTLP_ENDPOINT` is set, when the app boots, then `ObservabilityServiceProvider` exports traces and logs to that endpoint
- [ ] Given `ObservabilityServiceProvider` is already listed in the user's `providers.py`, when the app boots, then it is not registered twice (deduplication holds)

**Security Requirements**:
- [ ] Route logging must not emit handler function names or module paths that reveal internal structure to external log aggregators unless `LOG_LEVEL=DEBUG`

**Documentation Requirements**:
- [ ] Update `docs/site/docs/observability.md` noting observability is on by default from this version
- [ ] Add upgrade note in `docs/site/docs/upgrade.md` for the Uvicorn log suppression behavior change

**Priority**: Must
**Complexity**: Small
**Status**: Draft

---

### Story 4: `BaseService` lifecycle contract

**As a** framework user,
**I want** a `BaseService` abstract class with `connect()`, `disconnect()`, and `health_check()` methods,
**so that** I can wire my own services (and framework services like DB/cache/queue) into a single managed lifecycle without duplicating boot/shutdown logic across providers.

**Acceptance Criteria**:
- [ ] Given a class implements `BaseService`, when `application.register_service(my_service)` is called, then `my_service.connect()` is called during `Application.boot()` and `my_service.disconnect()` is called during `Application.shutdown()` in reverse registration order
- [ ] Given `BaseService.health_check()` returns `HealthResult(status=HealthStatus.healthy)`, when the health endpoint is called, then that service appears as `"healthy"` in the response
- [ ] Given `BaseService.health_check()` raises an exception, when the health endpoint is called, then that service appears as `"unhealthy"` with the exception message as `detail`
- [ ] Given `BaseService.connect()` raises, when `Application.boot()` runs, then a `BootError` is raised with the service name in the message
- [ ] Given `DatabaseServiceProvider` and `CacheManager`, when they are refactored to implement `BaseService`, then existing behaviour is unchanged (engine disposal, session factory)

**Security Requirements**:
- [ ] `health_check()` responses must not expose connection strings, credentials, or internal hostnames

**Documentation Requirements**:
- [ ] Add `docs/site/docs/services.md` with `BaseService` API reference and example

**Priority**: Must
**Complexity**: Medium
**Status**: Draft

---

### Story 5: Bootstrap health check endpoint

**As an** application operator,
**I want** a `/_health` endpoint that aggregates health checks from all registered `BaseService` instances,
**so that** load balancers, Kubernetes liveness/readiness probes, and monitoring tools can determine service health without custom code.

**Acceptance Criteria**:
- [ ] Given all services return `healthy`, when `GET /_health` is called, then the response is HTTP 200 with `{"status": "healthy", "checks": {...}}`
- [ ] Given any service returns `unhealthy`, when `GET /_health` is called, then the response is HTTP 503 with `{"status": "unhealthy", "checks": {...}}`
- [ ] Given a service returns `degraded`, when `GET /_health` is called, then the response is HTTP 200 with `{"status": "degraded", "checks": {...}}`
- [ ] Given multiple services, when `GET /_health` is called, then all `health_check()` methods are called concurrently (not sequentially)
- [ ] Given a health check takes longer than 5 seconds, when `GET /_health` is called, then that check times out and is reported as `unhealthy` with `"detail": "timeout"`
- [ ] Given `HEALTH_ALLOWED_CIDRS` is set, when a request originates outside the allowed CIDR range, then `GET /_health` returns HTTP 403

**Security Requirements**:
- [ ] `/_health` must support CIDR-based access restriction to prevent health data exposure to the public internet
- [ ] Individual check `detail` fields must not contain database connection strings or internal service URLs

**Documentation Requirements**:
- [ ] Add health check section to `docs/site/docs/deployment.md`

**Priority**: Must
**Complexity**: Small
**Status**: Draft

---

### Story 6: Global error handler via structured logging

**As a** framework user,
**I want** unhandled exceptions to be logged through arvel's `Log` facade (not stdlib `logging`),
**so that** 500 errors appear in my OTel pipeline and carry the active request context (request_id, user_id) alongside the traceback.

**Acceptance Criteria**:
- [ ] Given an unhandled exception occurs in a handler, when `HttpExceptionHandler._handle_unexpected` runs, then `Log.error("http.unhandled_exception", exc_info=True)` is called with active `Context` fields merged
- [ ] Given an unhandled exception occurs, when the HTTP response is sent, then the response body contains only a generic message (`"Internal server error"`) with no stack trace, SQL, or file paths
- [ ] Given a `NotFoundException` is raised with message `"User 42 not found"`, when the response is sent, then the response body carries that message (not a generic one)
- [ ] Given `ProblemDetailsHandler` is the default handler (RFC 7807), when a validation error occurs, then the response follows RFC 7807 (`type`, `title`, `status`, `detail`, `errors`)
- [ ] Given `HttpExceptionHandler` was previously used as the default, when the app upgrades, then existing JSON error shapes produced by typed exceptions (`BadRequestException`, `NotFoundException`, etc.) remain identical

**Security Requirements**:
- [ ] Stack traces must only appear in internal logs, never in HTTP responses (OWASP A10)
- [ ] Database error messages (e.g., unique constraint violations) must not surface in 500 responses

**Documentation Requirements**:
- [ ] Update `docs/site/docs/error-handling.md` with the new default handler and custom handler guide

**Priority**: Must
**Complexity**: Small
**Status**: Draft

---

### Story 7: Graceful shutdown with OS signal handling

**As an** application operator,
**I want** the arvel application to handle SIGTERM and SIGINT cleanly,
**so that** in-flight requests complete, services disconnect, and the process exits without data loss during rolling deployments or manual restarts.

**Acceptance Criteria**:
- [ ] Given the process receives SIGTERM, when uvicorn propagates the signal via ASGI lifespan shutdown, then `Application.shutdown()` is called and all registered `BaseService.disconnect()` methods run
- [ ] Given `GRACEFUL_SHUTDOWN_TIMEOUT=30` is set, when SIGTERM is received, then the `arvel serve` command passes `timeout_graceful_shutdown=30` to uvicorn
- [ ] Given an in-flight request is running when SIGTERM arrives, when uvicorn's graceful timeout elapses, then the connection is closed and the shutdown continues (no hang)
- [ ] Given `Application.shutdown()` completes, when the process exits, then exit code is `0` for clean shutdown and non-zero for forced kill
- [ ] Given a `BaseService.disconnect()` raises, when shutdown runs, then the error is logged and remaining services are still disconnected

**Security Requirements**:
- [ ] Shutdown must not leave open database transactions or uncommitted writes; `disconnect()` must roll back any pending sessions

**Documentation Requirements**:
- [ ] Add graceful shutdown section to `docs/site/docs/deployment.md`

**Priority**: Must
**Complexity**: Small
**Status**: Draft

---

### Story 8: Cache lock enhancements

**As a** framework user,
**I want** `CacheLock` to support TTL extension and configurable exponential backoff,
**so that** long-running operations can reliably hold locks without arbitrary fixed-poll delays or silent expiry.

**Acceptance Criteria**:
- [ ] Given a lock is held and `lock.extend(ttl=60)` is called, when the Redis store processes it, then the lock TTL is reset to 60 seconds only if the caller is the current owner
- [ ] Given `lock.extend(ttl)` is called by a non-owner, when the store processes it, then `False` is returned without modifying the lock
- [ ] Given `lock.block(timeout=10, backoff=0.1, max_backoff=2.0)` is called, when the lock is held by another process, then retry intervals grow exponentially up to `max_backoff`
- [ ] Given a non-Redis store (array, file, database) is configured, when `cache().lock("key")` is called, then a `RuntimeWarning` is emitted noting distributed-lock semantics are unavailable
- [ ] Given tests use `LockFake`, when `lock.acquire()` is called, then `fake.assert_acquired("key")` passes; when not acquired, `fake.assert_nothing_acquired()` passes

**Security Requirements**:
- [ ] Lock owners must be validated server-side (UUID check) before release or extension — no client-supplied owner bypass

**Documentation Requirements**:
- [ ] Update `docs/site/docs/cache.md` with `lock()` advanced usage section

**Priority**: Should
**Complexity**: Small
**Status**: Draft

---

### Story 9: Lifecycle regression test suite

**As a** framework maintainer,
**I want** a lifecycle regression test suite covering bootstrap ordering, middleware composition, observability wiring, and shutdown,
**so that** framework upgrades cannot silently break provider sequencing or middleware interaction.

**Acceptance Criteria**:
- [ ] Given the provider chain, when `Application.boot()` runs, then tests assert `ConfigServiceProvider` → `LogServiceProvider` → `ContextProvider` → `ObservabilityServiceProvider` → `DatabaseServiceProvider` → `HttpServiceProvider` run in that order
- [ ] Given `into_asgi()` is called, when the ASGI app is inspected, then tests assert `ContextMiddleware`, `ObservabilityMiddleware`, and `ArvelScopeMiddleware` are present in the middleware stack in the correct order
- [ ] Given a request is sent through the test client, when the response is returned, then tests assert `request_id` is present in the response headers and in captured log records
- [ ] Given SIGTERM is simulated, when the app shuts down, then tests assert all registered `BaseService.disconnect()` methods are called in reverse order
- [ ] Given a handler raises an unhandled exception, when the response is captured, then tests assert `Log.error` was called and the response body contains no stack trace

**Security Requirements**:
- [ ] Tests must use `anyio` backend isolation — no shared state between test cases

**Documentation Requirements**:
- [ ] None (tests are internal)

**Priority**: Must
**Complexity**: Medium
**Status**: Draft

---

## Dependencies

- Story 1 (`context/` module) must be complete before Story 2 (session-scoped logging) — logging reads from `Context`
- Story 4 (`BaseService`) must be complete before Story 5 (health endpoint) — endpoint calls `health_check()`
- Story 4 must be complete before Story 7 (graceful shutdown) — shutdown calls `disconnect()`
- Story 1, 2, 3 should be complete before Epic 002/003/004 — companion packages rely on the observability foundation

## Notes

- `ContextProvider` is added to the baseline HEAD chain between `LogServiceProvider` and `DatabaseServiceProvider`
- `ObservabilityServiceProvider` is added to the baseline HEAD chain after `ContextProvider`
- True per-request child DI containers (WI-002) are explicitly out of scope for this epic — `ArvelScopeMiddleware` improvement is a future work item
