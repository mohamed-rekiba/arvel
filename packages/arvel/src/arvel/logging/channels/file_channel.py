"""FileChannel — single and daily (rotating) file-backed log channel drivers."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import Any

from arvel.logging.channels.base import StdlibChannel


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


class SingleFileChannel(StdlibChannel):
    """Writes all log records to one file that is never rotated.

    Corresponds to Laravel's ``single`` channel driver.
    """

    def __init__(
        self,
        path: str,
        level: str = "info",
        bound: dict[str, object] | None = None,
    ) -> None:
        _ensure_parent(path)
        handler = logging.FileHandler(path, encoding="utf-8")
        super().__init__(handler, name=f"single.{path}", level=level, bound=bound)


class DailyFileChannel(StdlibChannel):
    """Writes to a file that is rotated at midnight; keeps ``days`` old files.

    Corresponds to Laravel's ``daily`` channel driver.
    """

    def __init__(
        self,
        path: str,
        days: int = 7,
        level: str = "info",
        bound: dict[str, object] | None = None,
    ) -> None:
        _ensure_parent(path)
        handler = logging.handlers.TimedRotatingFileHandler(
            path,
            when="midnight",
            backupCount=days,
            encoding="utf-8",
        )
        super().__init__(handler, name=f"daily.{path}", level=level, bound=bound)


def build_file_channel(cfg: dict[str, Any]) -> SingleFileChannel | DailyFileChannel:
    """Factory: ``{"driver": "single"|"daily", "path": "...", ...}``."""
    driver = cfg.get("driver", "single")
    path = str(cfg.get("path", "storage/logs/app.log"))
    level = str(cfg.get("level", "info"))
    if driver == "daily":
        days = int(cfg.get("days", 7))
        return DailyFileChannel(path=path, days=days, level=level)
    return SingleFileChannel(path=path, level=level)


__all__ = ["DailyFileChannel", "SingleFileChannel", "build_file_channel"]
