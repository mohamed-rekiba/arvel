"""Slow query detection — emits a WARNING log when a query exceeds the threshold."""

from __future__ import annotations


async def check_and_log_slow_query(
    *,
    sql: str,
    duration_ms: float,
    threshold_ms: int,
) -> None:
    """Emit a WARNING log if ``duration_ms`` exceeds ``threshold_ms``.

    Designed to be awaited from SQLAlchemy event hooks or a custom cursor proxy.
    """
    if duration_ms <= threshold_ms:
        return

    from arvel.logging.facade import Log

    Log.warning(
        "db.slow_query",
        sql=sql[:500],  # cap SQL length
        duration_ms=round(duration_ms, 2),
        threshold_ms=threshold_ms,
    )


__all__ = ["check_and_log_slow_query"]
