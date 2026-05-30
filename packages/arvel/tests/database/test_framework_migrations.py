"""Framework migration definitions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from arvel.auth.migrations.create_password_resets_table import down as down_password_resets
from arvel.auth.migrations.create_password_resets_table import up as up_password_resets
from arvel.auth.migrations.create_personal_access_tokens_table import down as down_tokens
from arvel.auth.migrations.create_personal_access_tokens_table import up as up_tokens
from arvel.auth.migrations.create_refresh_tokens_table import down as down_refresh_tokens
from arvel.auth.migrations.create_refresh_tokens_table import up as up_refresh_tokens
from arvel.auth.migrations.create_users_table import down as down_users
from arvel.auth.migrations.create_users_table import up as up_users
from arvel.cache.migrations.create_cache_table import down as down_cache
from arvel.cache.migrations.create_cache_table import up as up_cache
from arvel.database import Blueprint, Schema
from arvel.notifications.migrations.create_notifications_table import down as down_notifications
from arvel.notifications.migrations.create_notifications_table import up as up_notifications
from arvel.queue.migrations.create_failed_jobs_table import down as down_failed_jobs
from arvel.queue.migrations.create_failed_jobs_table import up as up_failed_jobs
from arvel.queue.migrations.create_jobs_table import down as down_jobs
from arvel.queue.migrations.create_jobs_table import up as up_jobs
from arvel.session.migrations.create_sessions_table import down as down_sessions
from arvel.session.migrations.create_sessions_table import up as up_sessions

Migration = tuple[
    str,
    Callable[[Schema], Awaitable[None]],
    Callable[[Schema], Awaitable[None]],
]


class _SchemaRecorder:
    def __init__(self) -> None:
        self.created: dict[str, list[str]] = {}
        self.dropped: list[str] = []

    def create(self, table_name: str, build: Callable[[Blueprint], None]) -> None:
        blueprint = Blueprint(table_name=table_name)
        build(blueprint)
        self.created[table_name] = [column.name for column in blueprint.columns]

    def drop_if_exists(self, table_name: str) -> None:
        self.dropped.append(table_name)


async def test_framework_migrations_define_expected_tables() -> None:
    migrations: list[Migration] = [
        ("users", up_users, down_users),
        ("password_resets", up_password_resets, down_password_resets),
        ("personal_access_tokens", up_tokens, down_tokens),
        ("refresh_tokens", up_refresh_tokens, down_refresh_tokens),
        ("cache", up_cache, down_cache),
        ("notifications", up_notifications, down_notifications),
        ("jobs", up_jobs, down_jobs),
        ("failed_jobs", up_failed_jobs, down_failed_jobs),
        ("sessions", up_sessions, down_sessions),
    ]
    recorder = _SchemaRecorder()
    schema = cast("Schema", recorder)

    for table_name, up, down in migrations:
        await up(schema)
        await down(schema)
        assert table_name in recorder.created
        assert table_name in recorder.dropped
        assert recorder.created[table_name]

    assert {"email", "password"}.issubset(recorder.created["users"])
    assert {"queue", "payload", "attempts"}.issubset(recorder.created["jobs"])
    assert {"id", "type", "data"}.issubset(recorder.created["notifications"])
