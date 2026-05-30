"""Application-level configuration values.

Read at runtime via ``arvel.config.lookup("app.name")``. Environment
overrides come from the process environment (``.env`` for local).
"""

from __future__ import annotations

from arvel.support.env import env as _env

name: str = _env("APP_NAME", "{{ project_name_pascal }}")
env: str = _env("APP_ENV", "production").lower()
debug: bool = _env("APP_DEBUG", default=False)
url: str = _env("APP_URL", "http://localhost:8000")
timezone: str = _env("APP_TIMEZONE", "UTC")
locale: str = _env("APP_LOCALE", "en")
is_production: bool = env == "production"
