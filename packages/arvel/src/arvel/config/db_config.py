"""Typed database configuration (``DB_*`` env vars)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.config.settings import ArvelSettings

# Maps the friendly DB_CONNECTION value to its async SQLAlchemy driver.
_DRIVER_MAP: dict[str, str] = {
    "postgresql": "postgresql+asyncpg",
    "postgres": "postgresql+asyncpg",
    "mysql": "mysql+aiomysql",
    "mariadb": "mysql+aiomysql",
    "sqlite": "sqlite+aiosqlite",
    "memory": "sqlite+aiosqlite",
}


class DbConfig(ArvelSettings):
    """Database connection settings.

    Two sources, in priority order:

    1. ``DB_URL`` — full SQLAlchemy async URL. Wins when set; all other
       fine-grained vars are ignored for the connection string itself
       (``echo``, ``pool_size``, ``max_overflow``, ``pool_recycle`` still
       come from their own vars).
    2. ``DB_CONNECTION`` + fine-grained ``DB_*`` — composed into a URL by
       ``async_url()``:

       - ``DB_CONNECTION``   friendly name: ``postgresql``, ``mysql``, ``sqlite``, ``memory``
       - ``DB_HOST``         (default: empty)
       - ``DB_PORT``         (default: 0)
       - ``DB_DATABASE``     (default: ``<base_path>/database/database.sqlite`` for sqlite,
                              ``:memory:`` when ``DB_CONNECTION=memory``)
       - ``DB_USERNAME``     (default: empty)
       - ``DB_PASSWORD``     (default: empty)
       - ``DB_ECHO``         bool; default ``False``
       - ``DB_POOL_SIZE``    (default: 5)
       - ``DB_MAX_OVERFLOW`` (default: 10)
       - ``DB_POOL_RECYCLE`` seconds; default 1800

    When neither ``DB_URL`` nor ``DB_CONNECTION`` is set the database
    subsystem is treated as **disabled** (``enabled == False``). The provider
    skips its startup ping and the engine falls back to ``sqlite+aiosqlite:///:memory:``
    so code that accidentally touches the ORM fails fast rather than
    silently persisting to a stale file.
    """

    model_config = SettingsConfigDict(env_prefix="DB_", extra="ignore")
    __config_path__ = "database.connections.{default}"

    # Full URL override — reads DB_URL.
    url: str | None = None
    # Friendly driver name — reads DB_CONNECTION.
    connection: str | None = None
    host: str = ""
    port: int = 0
    # Empty string → derive default path from base_path in async_url().
    database: str = ""
    username: str = ""
    password: SecretStr = Field(default=SecretStr(""))
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    pool_recycle: int = 1800

    @property
    def enabled(self) -> bool:
        """True when the database is explicitly configured via env."""
        return bool(self.url or self.connection)

    def async_url(self, base_path: Path | None = None) -> str:
        """Return the async SQLAlchemy URL.

        ``DB_URL`` wins when set. Otherwise the URL is built from
        ``DB_CONNECTION`` + fine-grained fields.

        ``base_path`` is used to resolve the default SQLite file path
        (``<base_path>/database/database.sqlite``) when ``DB_DATABASE``
        is not set and the driver is SQLite.
        """
        if self.url:
            return self.url
        conn = (self.connection or "").lower()
        driver = _DRIVER_MAP.get(conn, conn) if conn else "sqlite+aiosqlite"
        if driver.startswith("sqlite"):
            db = self.database
            if conn == "memory":
                db = ":memory:"
            elif not db:
                # No explicit DB_DATABASE: use canonical path when base_path given,
                # fall back to :memory: for ephemeral use (e.g. tests without base_path).
                db = (
                    str(base_path / "database" / "database.sqlite")
                    if base_path is not None
                    else ":memory:"
                )
            elif db != ":memory:" and not Path(db).is_absolute() and base_path is not None:
                db = str(base_path / db)
            if db == ":memory:":
                return "sqlite+aiosqlite:///:memory:"
            return f"{driver}:///{db}"
        userinfo = self.username
        secret = self.password.get_secret_value() if self.password else ""
        if secret:
            userinfo = f"{userinfo}:{secret}"
        if userinfo:
            userinfo = f"{userinfo}@"
        port = f":{self.port}" if self.port else ""
        return f"{driver}://{userinfo}{self.host}{port}/{self.database}"

    def public_repr(self) -> str:
        """Redacted summary safe for logs."""
        if self.url:
            return f"DbConfig(url={_redact_url(self.url)})"
        return f"DbConfig(connection={self.connection}, host={self.host}, database={self.database})"


def _redact_url(url: str) -> str:
    scheme_sep = url.find("://")
    if scheme_sep < 0:
        return "<malformed>"
    scheme, rest = url[:scheme_sep], url[scheme_sep + 3 :]
    at = rest.rfind("@")
    if at < 0:
        return f"{scheme}://{rest}"
    userinfo, hostpart = rest[:at], rest[at + 1 :]
    user_sep = userinfo.find(":")
    if user_sep < 0:
        return f"{scheme}://{userinfo}@{hostpart}"
    user = userinfo[:user_sep]
    return f"{scheme}://{user}:***@{hostpart}"


__all__ = ["DbConfig"]
