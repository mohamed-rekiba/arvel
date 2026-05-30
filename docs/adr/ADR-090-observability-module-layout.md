# ADR-090: `arvel/observability/` as the Module Home

**Date:** 2026-05-22
**Status:** Accepted
## Context

The current observability code lives under `arvel/logging_/`. With the addition
of metrics and traces, the module name `logging_` no longer describes the scope.

## Decision

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

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Put everything under `arvel/logging_/` | Module name misleading for metrics and traces |
| Rename `arvel/logging_/` to `arvel/observability/` | Would break `from arvel.logging_ import Log` for users who already wrote app code against the current API |
| New top-level `arvel/telemetry/` | `observability` is the established industry term |

## Consequences

- `arvel/providers/log_provider.py` is deleted; replaced by `arvel/observability/provider.py`.
- `arvel/database/query_logging.py` is deleted; OTel SQLAlchemy instrumentation replaces it.
- The `LogServiceProvider` entry-point in `pyproject.toml` is replaced by
  `ObservabilityServiceProvider` in the baseline provider list in `application.py`.
- `arvel/testing/observability.py` is a new file; `arvel/testing/` becomes the home for
  all test helpers (existing `RecordingLogManager` deleted from `arvel/logging_/testing.py`).
