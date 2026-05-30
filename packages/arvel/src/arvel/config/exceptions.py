"""Configuration-layer exceptions."""

from __future__ import annotations


class ConfigurationError(ValueError):
    """Raised when a required config value is missing or invalid."""


__all__ = ["ConfigurationError"]
