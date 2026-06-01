"""Cron-expression parsing and due-time evaluation, croniter-backed."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter


def is_valid_expression(expression: str) -> bool:
    """True if ``expression`` is a parseable cron expression."""
    return bool(croniter.is_valid(expression))


def is_due(
    expression: str,
    *,
    now: datetime,
    timezone: str = "UTC",
    tolerance_minutes: int = 1,
) -> bool:
    """True if a cron fire time exists in the window ``(now - tolerance, now]``.

    The default 1-minute tolerance matches Laravel's per-minute scheduler tick:
    if the cron expression matches the current minute, the task is due.
    """
    tz = ZoneInfo(timezone)
    now_aware = now.astimezone(tz)
    window_start = now_aware - timedelta(minutes=tolerance_minutes)
    # Find the first fire time after window_start; if it's <= now, we're due.
    it = croniter(expression, window_start)
    next_fire: datetime = it.get_next(datetime)
    return next_fire <= now_aware


__all__ = ["is_due", "is_valid_expression"]
