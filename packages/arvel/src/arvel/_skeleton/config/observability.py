"""Observability configuration.

Re-exports :class:`ObservabilityConfig` so apps can tune OTel via env vars
(``OTEL_*``) without subclassing. Copy and edit if you need app-specific
defaults.
"""

from __future__ import annotations

from arvel.observability.config import ObservabilityConfig

__all__ = ["ObservabilityConfig"]
