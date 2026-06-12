"""Logging configuration.

Namespaced so it never shadows the stdlib ``logging`` module — the
loader registers this under ``_arvel_user_app.config.logging``.
"""

from __future__ import annotations

from arvel.support.env import env

default: str = env("LOG_CHANNEL", "stack")

channels: dict[str, dict[str, object]] = {
    # Stack fan-out example: write to otel and a local file simultaneously.
    "stack": {"driver": "stack", "channels": ["otel"]},
    # OTel — routes to OTLP collector when OTLP_ENDPOINT is set, otherwise
    # renders formatted lines to stdout. This is the production default.
    "otel": {"driver": "otel"},
    # Single file — never rotated; good for low-volume apps or dev.
    "single": {
        "driver": "single",
        "path": "storage/logs/app.log",
        "level": env("LOG_LEVEL", "info"),
    },
    # Daily rotating file — keeps 14 days of archives.
    "daily": {"driver": "daily", "path": "storage/logs/app.log", "days": 14},
    # Stderr — writes to sys.stderr; handy in Docker where stdout goes to OTel.
    "stderr": {"driver": "stderr", "level": env("LOG_LEVEL", "info")},
    # Null — discards every record; useful in tests.
    "null": {"driver": "null"},
}
