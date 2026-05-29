"""Database configuration.

The default is SQLite so a freshly generated project boots with zero
infrastructure. Set ``DB_CONNECTION`` and the relevant ``DB_*`` vars (or
the single ``DB_URL``) to switch to Postgres or MySQL.

For simple single-connection setups you don't need this file at all — the
framework reads ``DB_CONNECTION``, ``DB_URL``, etc. directly via ``DbConfig``.
Keep this file when you need multiple named connections or want explicit
control over the pool.
"""

from __future__ import annotations

from arvel.support.env import env
from arvel.support.str import Str

_url = env("DB_URL", "")
_host = env("DB_HOST", "127.0.0.1")
_port = env("DB_PORT", "5432")
_database = env("DB_DATABASE", "")
_username = env("DB_USERNAME", "")
_password = env("DB_PASSWORD", "")
_pool_size = int(env("DB_POOL_SIZE", "5"))
_max_overflow = int(env("DB_MAX_OVERFLOW", "10"))
_pool_recycle = int(env("DB_POOL_RECYCLE", "1800"))
_echo = Str.to_bool(env("DB_ECHO", "False"))

default: str = env("DB_CONNECTION", "sqlite")


def _connection_url(driver: str) -> str:
    userinfo = _username
    if _password:
        userinfo = f"{userinfo}:{_password}"
    if userinfo:
        userinfo = f"{userinfo}@"
    port = f":{_port}" if _port else ""
    return f"{driver}://{userinfo}{_host}{port}/{_database}"


connections: dict[str, dict[str, object]] = {
    "memory": {
        "url": "sqlite+aiosqlite:///:memory:",
        "echo": _echo,
    },
    "sqlite": {
        "url": _url or "sqlite+aiosqlite:///database/database.sqlite",
        "echo": _echo,
    },
    "postgresql": {
        "url": _url or _connection_url("postgresql+asyncpg"),
        "host": _host,
        "port": _port,
        "database": _database,
        "username": _username,
        "password": _password,
        "echo": _echo,
        "pool_size": _pool_size,
        "max_overflow": _max_overflow,
        "pool_recycle": _pool_recycle,
    },
    "mysql": {
        "url": _url or _connection_url("mysql+aiomysql"),
        "host": _host,
        "port": _port,
        "database": _database,
        "username": _username,
        "password": _password,
        "echo": _echo,
        "pool_size": _pool_size,
        "max_overflow": _max_overflow,
        "pool_recycle": _pool_recycle,
    },
}
