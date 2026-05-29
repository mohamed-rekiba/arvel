"""Mail configuration — Mailpit catches every outgoing email in dev/test."""

from __future__ import annotations

from arvel.support.env import env

default: str = "smtp"

mailers: dict[str, dict[str, object]] = {
    "smtp": {
        "transport": "smtp",
        "host": env("MAIL_HOST", "localhost"),
        "port": env("MAIL_PORT", 1025),
        "username": env("MAIL_USERNAME") or None,
        "password": env("MAIL_PASSWORD") or None,
        "encryption": env("MAIL_ENCRYPTION") or None,
    },
    "log": {
        "transport": "log",
    },
}

from_address: str = env("MAIL_FROM_ADDRESS", "noreply@example.com")
from_name: str = env("MAIL_FROM_NAME", "Arvel Demo")
