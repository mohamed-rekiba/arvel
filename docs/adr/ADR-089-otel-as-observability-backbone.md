# ADR-089: OTel SDK as the Observability Backbone

**Date:** 2026-05-22
**Status:** Accepted
## Context

Arvel has a partial custom logging stack (`arvel/logging_/`) with a plain-text
stderr driver and several file/syslog/Slack drivers. Metrics and tracing are
documented but not implemented. `structlog` is used ad-hoc with no central
configuration. The stack does not integrate with any standard observability
backend.

## Decision

Replace the custom driver stack in full with the **OpenTelemetry Python SDK**
as the backbone for all three observability signals (logs, metrics, traces).

The OTel SDK is the vendor-neutral, CNCF-graduated standard for observability.
It produces signals in OTLP format accepted by every major backend (Grafana,
Datadog, Honeycomb, Jaeger, Google Cloud Trace, AWS X-Ray, etc.) without
changing application code.

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Keep custom driver stack, add JSON output | Solves logging only; metrics and traces would still require separate libs |
| structlog + structlog-otel bridge | Surfaces structlog idioms to app devs; two mental models |
| Bare OTel SDK exposed directly | Too much OTel SDK knowledge required from app developers |

## Consequences

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
