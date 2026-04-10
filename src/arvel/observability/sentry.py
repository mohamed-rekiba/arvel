"""Sentry integration — optional dependency, no-op when not installed or not configured."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.observability.config import ObservabilitySettings

_HAS_SENTRY = False
try:
    import sentry_sdk

    _HAS_SENTRY = True
except ImportError:
    pass


def configure_sentry(settings: ObservabilitySettings) -> bool | None:
    """Initialize Sentry SDK if DSN is configured and sentry-sdk is installed.

    Returns True if Sentry was initialized, None/False otherwise.
    """
    if not settings.sentry_dsn:
        return None

    if not _HAS_SENTRY:
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    return True
