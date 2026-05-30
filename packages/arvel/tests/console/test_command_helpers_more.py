"""Console command helper coverage."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from arvel.console.commands import auth_clear_resets, db_show, db_table
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection


def test_db_show_collects_database_info() -> None:
    collect = cast(
        "Callable[[Connection], db_show.DatabaseInfo]",
        object.__getattribute__(db_show, "_collect_database_info"),
    )
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id integer primary key, email varchar)"))
            info = collect(conn)
    finally:
        engine.dispose()

    assert info.driver == "sqlite"
    assert info.database == ":memory:"
    assert info.tables == ["users"]


def test_db_table_collects_columns_indexes_and_missing_table() -> None:
    collect = cast(
        "Callable[[Connection, str], dict[str, list[dict[str, object]]] | None]",
        object.__getattribute__(db_table, "_collect_table_details"),
    )
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE users (id integer primary key, email varchar NOT NULL)")
            )
            conn.execute(text("CREATE INDEX ix_users_email ON users (email)"))
            details = collect(conn, "users")
            missing = collect(conn, "missing")
    finally:
        engine.dispose()

    assert missing is None
    assert details is not None
    assert details["columns"][0]["name"] == "id"
    assert details["columns"][1]["nullable"] is False
    assert details["indexes"] == [{"name": "ix_users_email", "columns": ["email"]}]


def test_auth_clear_resets_deletes_expired_rows() -> None:
    delete_expired = cast(
        "Callable[[Connection], int]",
        object.__getattribute__(auth_clear_resets, "_delete_expired"),
    )
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE password_reset_tokens ("
                    "email varchar primary key, token varchar, created_at datetime)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO password_reset_tokens (email, token, created_at) VALUES "
                    "('old@example.test', 'old', datetime('now', '-7200 seconds')), "
                    "('new@example.test', 'new', datetime('now'))"
                )
            )
            assert delete_expired(conn) == 1
            remaining = (
                conn.execute(text("SELECT email FROM password_reset_tokens")).scalars().all()
            )
    finally:
        engine.dispose()

    assert remaining == ["new@example.test"]


def test_auth_clear_resets_raises_for_missing_table() -> None:
    delete_expired = cast(
        "Callable[[Connection], int]",
        object.__getattribute__(auth_clear_resets, "_delete_expired"),
    )
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn, pytest.raises(RuntimeError, match="does not exist"):
            delete_expired(conn)
    finally:
        engine.dispose()
