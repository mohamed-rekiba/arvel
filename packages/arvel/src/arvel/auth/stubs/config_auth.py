"""Auth configuration stub — published to config/auth.py by `arvel auth:install`.

Edit this file to customise guards, providers, and JWT settings.
"""

from __future__ import annotations

from arvel.support.env import env

default: str = "web"

guards: dict[str, dict[str, str]] = {
    "web": {
        "driver": "session",
        "provider": "users",
    },
    "api": {
        "driver": "jwt",
        "provider": "users",
    },
}

providers: dict[str, dict[str, str]] = {
    "users": {
        "driver": "database",
        "model": "app.models.user.User",
    },
}

jwt: dict[str, str | int] = {
    # Must be at least 32 characters. Generate one with `arvel key:generate`.
    "secret": env("JWT_SECRET", ""),
    "algorithm": "HS256",
    "ttl_seconds": 900,
    "issuer": env("JWT_ISSUER", ""),
    "audience": env("JWT_AUDIENCE", ""),
}

refresh: dict[str, str | int | bool] = {
    "ttl_seconds": 14 * 24 * 3600,
    "cookie_name": "__Host-refresh",
    "cookie_secure": True,
}

routes: dict[str, str | bool] = {
    "enabled": True,
    "prefix": "/api/auth",
}

# Base URL of your front-end password-reset page (not the full link). The reset
# email appends ?token=...&email=... to this. Empty falls back to
# {app.url}/reset-password.
reset_page_url: str = env("AUTH_RESET_PAGE_URL", "")
