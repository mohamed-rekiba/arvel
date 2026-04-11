"""Static configuration data for the `arvel new` command."""

from __future__ import annotations

from typing import Any

FRAMEWORK_REPO = "mohamed-rekiba/arvel"

_BUNDLED_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "default",
        "description": (
            "Official Arvel starter — full app skeleton with modular"
            " monolith structure, config, routes, tests, and database"
            " setup."
        ),
        "repo": "https://github.com/mohamed-rekiba/arvel-starter",
        "default": True,
    },
]

DATABASE_CONFIGS: dict[str, dict[str, str]] = {
    "sqlite": {
        "driver": "sqlite",
        "sa_driver": "sqlite+aiosqlite",
        "url_template": "sqlite+aiosqlite:///database/database.sqlite",
        "extra": "sqlite",
        "db_host": "",
        "db_port": "",
        "db_username": "",
        "db_password": "",
        "db_database": "database/database.sqlite",
    },
    "postgres": {
        "driver": "pgsql",
        "sa_driver": "postgresql+asyncpg",
        "url_template": "postgresql+asyncpg://localhost:5432/{app_name}",
        "extra": "pg",
        "db_host": "127.0.0.1",
        "db_port": "5432",
        "db_username": "arvel",
        "db_password": "{app_name}",
        "db_database": "{app_name}",
    },
    "mysql": {
        "driver": "mysql",
        "sa_driver": "mysql+aiomysql",
        "url_template": "mysql+aiomysql://localhost:3306/{app_name}",
        "extra": "mysql",
        "db_host": "127.0.0.1",
        "db_port": "3306",
        "db_username": "arvel",
        "db_password": "{app_name}",
        "db_database": "{app_name}",
    },
}

CACHE_CONFIGS: dict[str, dict[str, str]] = {
    "memory": {"driver": "memory", "extra": ""},
    "redis": {"driver": "redis", "extra": "redis"},
}

QUEUE_CONFIGS: dict[str, dict[str, str]] = {
    "sync": {"driver": "sync", "extra": ""},
    "redis": {"driver": "redis", "extra": "redis"},
    "taskiq": {"driver": "taskiq", "extra": "taskiq"},
}

MAIL_CONFIGS: dict[str, dict[str, str]] = {
    "log": {"driver": "log", "extra": ""},
    "smtp": {"driver": "smtp", "extra": "smtp"},
}

STORAGE_CONFIGS: dict[str, dict[str, str]] = {
    "local": {"driver": "local", "extra": ""},
    "s3": {"driver": "s3", "extra": "s3"},
}

SEARCH_CONFIGS: dict[str, dict[str, str]] = {
    "collection": {"driver": "collection", "extra": ""},
    "meilisearch": {"driver": "meilisearch", "extra": "meilisearch"},
    "elasticsearch": {"driver": "elasticsearch", "extra": "elasticsearch"},
}

BROADCAST_CONFIGS: dict[str, dict[str, str]] = {
    "memory": {"driver": "memory", "extra": ""},
    "redis": {"driver": "redis", "extra": "redis"},
    "log": {"driver": "log", "extra": ""},
    "null": {"driver": "null", "extra": ""},
}

_VALID_CHOICES: dict[str, dict[str, dict[str, str]]] = {
    "database": DATABASE_CONFIGS,
    "cache": CACHE_CONFIGS,
    "queue": QUEUE_CONFIGS,
    "mail": MAIL_CONFIGS,
    "storage": STORAGE_CONFIGS,
    "search": SEARCH_CONFIGS,
    "broadcast": BROADCAST_CONFIGS,
}


PRESETS: dict[str, dict[str, str]] = {
    "minimal": {
        "database": "sqlite",
        "cache": "memory",
        "queue": "sync",
        "mail": "log",
        "storage": "local",
        "search": "collection",
        "broadcast": "memory",
    },
    "standard": {
        "database": "postgres",
        "cache": "redis",
        "queue": "redis",
        "mail": "smtp",
        "storage": "local",
        "search": "collection",
        "broadcast": "memory",
    },
    "full": {
        "database": "postgres",
        "cache": "redis",
        "queue": "taskiq",
        "mail": "smtp",
        "storage": "s3",
        "search": "meilisearch",
        "broadcast": "redis",
    },
}

_SERVICE_LABELS: dict[str, str] = {
    "database": "Database",
    "cache": "Cache",
    "queue": "Queue",
    "mail": "Mail",
    "storage": "Storage",
    "search": "Search",
    "broadcast": "Broadcast",
}
