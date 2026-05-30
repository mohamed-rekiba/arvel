"""Logging configuration."""

from __future__ import annotations

from arvel.support.env import env

default: str = env("LOG_CHANNEL", "stack")

channels: dict[str, dict[str, object]] = {
    "stack": {
        "driver": "stack",
        "channels": ["stderr"],
        "level": env("LOG_LEVEL", "info"),
        "formatter": env("LOG_FORMAT", "json"),  # "json" or "console"
    },
    "stderr": {
        "driver": "stderr",
        "level": env("LOG_LEVEL", "info"),
        "formatter": env("LOG_FORMAT", "json"),
    },
    "single": {
        "driver": "single",
        "path": "storage/logs/app.log",
        "level": env("LOG_LEVEL", "info"),
    },
}
