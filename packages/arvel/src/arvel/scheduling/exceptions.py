"""Scheduling-specific exceptions."""

from __future__ import annotations


class ScheduleError(Exception):
    """Raised at task-registration time for invalid expressions or modifiers."""


__all__ = ["ScheduleError"]
