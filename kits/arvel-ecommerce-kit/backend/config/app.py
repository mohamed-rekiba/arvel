"""Application-level configuration."""

from __future__ import annotations

from arvel.support.env import env as _env

name: str = _env("APP_NAME", "Arvel E-Commerce Kit")
env: str = _env("APP_ENV", "production").lower()
debug: bool = _env("APP_DEBUG", default=False)
url: str = _env("APP_URL", "http://localhost:8000")
timezone: str = _env("APP_TIMEZONE", "UTC")
locale: str = _env("APP_LOCALE", "en")
fallback_locale: str = _env("APP_FALLBACK_LOCALE", "en")
key: str = _env("APP_KEY", "")  # required in production; signed-URL secret
is_production: bool = env == "production"
