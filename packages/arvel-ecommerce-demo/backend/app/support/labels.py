"""Helpers for human-friendly log breadcrumbs."""

from __future__ import annotations

from typing import Any


def label(value: Any) -> str:
    """Best-effort display name for a breadcrumb — first translation or the raw value."""
    if isinstance(value, dict):
        return next((str(v) for v in value.values() if v), "")
    return str(value) if value else ""


__all__ = ["label"]
