"""Str case conversion helpers."""

from __future__ import annotations

import pytest
from arvel.support.str import Str


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CreateUsersTable", "create_users_table"),
        ("UserProfile", "user_profile"),
        ("userProfile", "user_profile"),
        ("user_profile", "user_profile"),
        ("user-profile", "user_profile"),
        ("User Profile", "user_profile"),
        ("HTTPServer", "http_server"),
        ("HTTP2Server", "http2_server"),
        ("APIv1Client", "ap_iv1_client"),
        ("a", "a"),
        ("A", "a"),
        ("alreadysnake", "alreadysnake"),
        ("_user", "user"),
        ("user_", "user"),
        ("__double__", "double"),
        ("---", ""),
        ("", ""),
    ],
)
def test_snake(raw: str, expected: str) -> None:
    assert Str.snake(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CreateUsersTable", "createUsersTable"),
        ("create_users_table", "createUsersTable"),
        ("create-users-table", "createUsersTable"),
        ("createUsersTable", "createUsersTable"),
        ("user profile", "userProfile"),
        ("a", "a"),
        ("A", "a"),
        ("", ""),
        ("---", ""),
    ],
)
def test_camel(raw: str, expected: str) -> None:
    assert Str.camel(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("create_users_table", "CreateUsersTable"),
        ("create-users-table", "CreateUsersTable"),
        ("createUsersTable", "CreateUsersTable"),
        ("CreateUsersTable", "CreateUsersTable"),
        ("user profile", "UserProfile"),
        ("a", "A"),
        ("", ""),
        ("---", ""),
    ],
)
def test_pascal(raw: str, expected: str) -> None:
    assert Str.pascal(raw) == expected


def test_snake_is_idempotent() -> None:
    once = Str.snake("CreateUsersTable")
    assert Str.snake(once) == once


def test_pascal_is_idempotent() -> None:
    once = Str.pascal("create_users_table")
    assert Str.pascal(once) == once


def test_camel_is_idempotent() -> None:
    once = Str.camel("create_users_table")
    assert Str.camel(once) == once
