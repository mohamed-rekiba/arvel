"""Observability package — structured logging, request-ID, access log, health, tracing, Sentry."""

from __future__ import annotations

from arvel.observability.access_log import AccessLogMiddleware
from arvel.observability.config import ObservabilitySettings
from arvel.observability.health import HealthCheck, HealthRegistry, HealthResult, HealthStatus
from arvel.observability.logging import (
    ContextProcessor,
    RedactProcessor,
    RequestIdProcessor,
    configure_logging,
)
from arvel.observability.provider import ObservabilityProvider
from arvel.observability.request_id import (
    RequestIdMiddleware,
    get_request_id,
    request_id_var,
)
from arvel.observability.sentry import configure_sentry
from arvel.observability.tracing import configure_tracing, get_tracer

__all__ = [
    "AccessLogMiddleware",
    "ContextProcessor",
    "HealthCheck",
    "HealthRegistry",
    "HealthResult",
    "HealthStatus",
    "ObservabilityProvider",
    "ObservabilitySettings",
    "RedactProcessor",
    "RequestIdMiddleware",
    "RequestIdProcessor",
    "configure_logging",
    "configure_sentry",
    "configure_tracing",
    "get_request_id",
    "get_tracer",
    "request_id_var",
]
