"""Phase G / It.9 — logging channel() keeps bound context (M6); request-id + locale middleware are
wired into the default global stack (M3). (Kernel diagnostics also now use the framework LogManager,
not stdlib logging — verified by the suite + a no-stdlib-logging check.)"""

from __future__ import annotations

from structlog.testing import capture_logs

from arvel.http import HttpKernel
from arvel.http.middleware import LocaleMiddleware, RequestContextMiddleware
from arvel.kernel.logging import LogManager


def test_channel_preserves_already_bound_context() -> None:
    with capture_logs() as logs:
        LogManager().bind(tenant="acme").channel("billing").info("charged")
    assert logs[0]["event"] == "charged"
    assert logs[0]["tenant"] == "acme"  # M6: channel() kept the prior bind (was discarded before)
    assert logs[0]["channel"] == "billing"


def test_use_default_global_wires_request_id_first_and_locale() -> None:
    kernel = HttpKernel()
    kernel.use_default_global()
    # request-id first so every later log event carries it; locale present (M3)
    assert kernel.global_middleware[0] is RequestContextMiddleware
    assert LocaleMiddleware in kernel.global_middleware
    # idempotent — calling again doesn't duplicate
    kernel.use_default_global()
    assert kernel.global_middleware.count(RequestContextMiddleware) == 1
