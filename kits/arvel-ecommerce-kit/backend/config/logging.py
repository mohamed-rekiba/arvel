"""Logging configuration."""

from __future__ import annotations

from arvel.support.env import env

default: str = env("LOG_CHANNEL", "stack")

channels: dict[str, dict[str, object]] = {
    # Primary channel: fans out to otel.  otel routes to OTLP when the
    # endpoint is configured, otherwise falls back to stdout — so this works
    # in both local dev and production without changing the channel name.
    "stack": {
        "driver": "stack",
        "channels": ["otel"],
    },
    "otel": {"driver": "otel"},
    "stderr": {
        "driver": "stderr",
        "level": env("LOG_LEVEL", "info"),
    },
    "single": {
        "driver": "single",
        "path": "storage/logs/app.log",
        "level": env("LOG_LEVEL", "info"),
    },
}
