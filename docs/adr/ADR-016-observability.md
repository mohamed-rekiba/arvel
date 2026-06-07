# ADR-016 — Observability

**Status**: Accepted
**Date**: original decisions 2026-06-07 – 2026-06-07; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: OpenTelemetry as the backbone, observability module layout, middleware placement.

## Why this is one ADR

OTel chassis, where the code lives, and where it plugs into the request pipeline — three decisions, one design.

---

## § 1 — OTel SDK as the Observability Backbone

**Originally**: ADR-118

### Context

Arvel has a partial custom logging stack (`arvel/logging_/`) with a plain-text
stderr driver and several file/syslog/Slack drivers. Metrics and tracing are
documented but not implemented. `structlog` is used ad-hoc with no central
configuration. The stack does not integrate with any standard observability
backend.

### Decision

Replace the custom driver stack in full with the **OpenTelemetry Python SDK**
as the backbone for all three observability signals (logs, metrics, traces).

The OTel SDK is the vendor-neutral, CNCF-graduated standard for observability.
It produces signals in OTLP format accepted by every major backend (Grafana,
Datadog, Honeycomb, Jaeger, Google Cloud Trace, AWS X-Ray, etc.) without
changing application code.

### Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Keep custom driver stack, add JSON output | Solves logging only; metrics and traces would still require separate libs |
| structlog + structlog-otel bridge | Surfaces structlog idioms to app devs; two mental models |
| Bare OTel SDK exposed directly | Too much OTel SDK knowledge required from app developers |

### Consequences

- **Positive:** Vendor-neutral; single pipeline for logs + metrics + traces; standard
  correlation IDs; OTLP export to any collector; community-maintained instrumentations
  for FastAPI, SQLAlchemy, etc.
- **Positive:** The `Log` facade keeps its ergonomic API; internals are hidden.
- **Negative:** OTel Python Logs SDK is still marked "Development" in the project status
  (though the pypi package is Production/Stable). This is a known OTel project maturity
  caveat; the API is stable enough for production use.
- **Negative:** `opentelemetry-instrumentation-*` packages use 0.x Beta versioning
  (standard for OTel Python contrib); update churn is expected with minor SDK releases.
- **Action:** Pin all OTel dependencies with `>=X.Y.Z,<X.(Y+2).0` ranges; run
  `uv pip compile` at each minor SDK bump to verify the resolved set.

---

## § 2 — `arvel/observability/` as the Module Home

**Originally**: ADR-119

### Context

The current observability code lives under `arvel/logging_/`. With the addition
of metrics and traces, the module name `logging_` no longer describes the scope.

### Decision

Create a new `arvel/observability/` module as the home for:
- `ObservabilityServiceProvider`
- `ObservabilityConfig`
- `ObservabilityMiddleware`
- Context vars (`_request_id`, `_user_id`, `_route`)
- `metrics_route.py` (Prometheus endpoint)

The `arvel/logging_/` module is retained but slimmed to:
- `facade.py` — `Log` facade (rewritten internals against OTel)
- `otel_logger.py` — OTel-backed `Logger` implementation
- `protocols.py` — `Logger` protocol (unchanged)
- `__init__.py` — re-exports (`Log`, `Logger`)

`from arvel.facades import Log` is added as the canonical import.
`from arvel.logging_ import Log` remains as a re-export.

### Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Put everything under `arvel/logging_/` | Module name misleading for metrics and traces |
| Rename `arvel/logging_/` to `arvel/observability/` | Would break `from arvel.logging_ import Log` for users who already wrote app code against the current API |
| New top-level `arvel/telemetry/` | `observability` is the established industry term |

### Consequences

- `arvel/providers/log_provider.py` is deleted; replaced by `arvel/observability/provider.py`.
- `arvel/database/query_logging.py` is deleted; OTel SQLAlchemy instrumentation replaces it.
- The `LogServiceProvider` entry-point in `pyproject.toml` is replaced by
  `ObservabilityServiceProvider` in the baseline provider list in `application.py`.
- `arvel/testing/observability.py` is a new file; `arvel/testing/` becomes the home for
  all test helpers (existing `RecordingLogManager` deleted from `arvel/logging_/testing.py`).

---

## § 3 — ObservabilityMiddleware Placement (Outermost, Before Auth)

**Originally**: ADR-120

### Context

`ObservabilityMiddleware` needs to open an OTel span for the full request lifecycle,
propagate `traceparent` headers, and inject `request_id` into the log context.
The auth middleware (`JwtGuard` / `AuthenticateMiddleware`) must run before `user_id`
is known. There is a tension: the middleware must be outermost to measure total
request duration, but `user_id` is only available after auth resolves.

### Decision

Register `ObservabilityMiddleware` as the **outermost middleware** (added first in
the Starlette middleware stack, so it wraps everything else). The middleware
binds `request_id` and `route` before the request begins, then reads
`request.state.user_id` in a post-response hook (after `await call_next(request)`)
to late-bind `user_id` into the span attributes and log context.

This means:
- `request_id`, `route`, `service` are available on all log records in the request.
- `user_id` is present on log records emitted AFTER `call_next` returns (error logs,
  response hooks) but NOT on log records emitted during request processing by the
  route handler itself — unless the handler explicitly calls
  `Log.with_context(user_id=...)`.
- The span's `user_id` attribute is set after the span is active, which is supported
  by the OTel SDK.

### Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Register ObservabilityMiddleware after auth middleware | User_id available, but span doesn't cover auth time; loses timing accuracy |
| Two middlewares (outer for span/request_id, inner for user_id) | Complexity; user_id still not in handler-time logs |
| Inject user_id via a request lifecycle hook in the auth layer | Couples auth to observability; wrong boundary |

### Consequences

- Handler-time log records won't carry `user_id` unless the app calls
  `Log.with_context(user_id=current_user.id)` in a dependency or handler.
  This is documented as the expected pattern.
- The DX guide recommends a `get_current_user` FastAPI dependency that also calls
  `Log.with_context(user_id=user.id)` so all handler logs carry the user.
- `request_id` and OTel span are fully reliable for all log correlation even without
  `user_id`.

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-118 | — | OTel SDK as the Observability Backbone | § 1 |
| ADR-119 | — | `arvel/observability/` as the Module Home | § 2 |
| ADR-120 | — | ObservabilityMiddleware Placement (Outermost, Before Auth) | § 3 |
