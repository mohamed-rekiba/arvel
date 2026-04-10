"""Database configuration settings."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


class DatabaseSettings(ModuleSettings):
    """Database connection and pool configuration.

    All fields are prefixed with DB_ in environment variables.

    Pool defaults follow SA recommended practices:
    - ``pool_pre_ping=True`` detects stale connections from DB restarts
    - ``pool_recycle=3600`` prevents long-lived connections from going stale
    - ``expire_on_commit=False`` prevents lazy-load errors after commit in async
    """

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        extra="ignore",
    )

    config_name: ClassVar[str] = "database"

    db_url: str | None = Field(default=None, validation_alias="DB_URL")
    driver: Literal["sqlite", "pgsql", "postgres", "postgresql", "mysql"] = "sqlite"
    host: str = "127.0.0.1"
    port: int = 5432
    database: str = "database/database.sqlite"
    username: str = "arvel"
    password: SecretStr = SecretStr("")
    echo: bool = False
    pool_size: int = 10
    pool_max_overflow: int = 5
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True
    expire_on_commit: bool = False

    @property
    def url(self) -> str:
        """Resolve DB URL from DB_URL or structured DB_* values."""
        if self.db_url:
            return self.db_url

        if self.driver == "sqlite":
            db_path = Path(self.database)
            if db_path.is_absolute():
                return f"sqlite+aiosqlite:///{db_path}"
            normalized = db_path.as_posix().lstrip("./")
            return f"sqlite+aiosqlite:///{normalized}"

        if self.driver in {"pgsql", "postgres", "postgresql"}:
            dialect = "postgresql+asyncpg"
        else:
            dialect = "mysql+aiomysql"

        raw_password = self.password.get_secret_value()
        credentials = self.username if not raw_password else f"{self.username}:{raw_password}"
        return f"{dialect}://{credentials}@{self.host}:{self.port}/{self.database}"


settings_class = DatabaseSettings
