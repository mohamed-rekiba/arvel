"""Public logger facade errors."""

from __future__ import annotations


class UnknownLogChannelError(ValueError):
    """Raised when selecting a channel that is not configured."""


class InvalidLogChannelConfigurationError(ValueError):
    """Raised when channel registry configuration is invalid."""
