"""Logging configuration.

Namespaced so it never shadows the stdlib ``logging`` module — the
loader registers this under ``_arvel_user_app.config.logging``.
"""

from __future__ import annotations

from arvel.support.env import env

default: str = "stack"

channels: dict[str, dict[str, str]] = {
    "stack": {"driver": "stack", "level": env("LOG_LEVEL", "info")},
    "single": {"driver": "single", "path": "storage/logs/app.log"},
    "stderr": {"driver": "stderr", "level": env("LOG_LEVEL", "info")},
}
