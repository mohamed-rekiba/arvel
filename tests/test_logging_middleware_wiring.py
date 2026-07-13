"""logging channel() keeps bound context (M6); request-id + locale middleware wired into the default
global stack (M3)."""

from __future__ import annotations

from structlog.testing import capture_logs

from arvel.http import HttpKernel
from arvel.http.middleware import (
    ConvertEmptyStringsToNull,
    LocaleMiddleware,
    RequestContextMiddleware,
    TrimStrings,
    ValidateHost,
)
from arvel.kernel.logging import LogManager
from arvel.telemetry.middleware import TelemetryMiddleware


def test_channel_preserves_already_bound_context() -> None:
    with capture_logs() as logs:
        LogManager().bind(tenant="acme").channel("billing").info("charged")
    assert logs[0]["event"] == "charged"
    assert logs[0]["tenant"] == "acme"  # M6: channel() kept the prior bind (was discarded before)
    assert logs[0]["channel"] == "billing"


def test_use_default_global_wires_request_id_first_and_locale() -> None:
    kernel = HttpKernel()
    kernel.use_default_global()
    # telemetry outermost; request-id next so every later log event carries it; locale present (M3)
    assert kernel.global_middleware[0] is TelemetryMiddleware
    assert kernel.global_middleware[1] is RequestContextMiddleware
    assert LocaleMiddleware in kernel.global_middleware
    # idempotent — calling again doesn't duplicate
    kernel.use_default_global()
    assert kernel.global_middleware.count(RequestContextMiddleware) == 1


def test_use_default_global_wires_normalization_between_host_and_locale() -> None:
    """H8: TrimStrings, then ConvertEmptyStringsToNull, land after ValidateHost and before
    LocaleMiddleware (so they run for every request, not just session/CSRF ones)."""
    kernel = HttpKernel()
    kernel.use_default_global()
    order = kernel.global_middleware
    assert (
        order.index(ValidateHost)
        < order.index(TrimStrings)
        < order.index(ConvertEmptyStringsToNull)
        < order.index(LocaleMiddleware)
    )
