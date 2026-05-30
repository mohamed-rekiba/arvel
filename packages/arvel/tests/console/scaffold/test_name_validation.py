"""FR-004-002: project-name validation against ``^[a-z][a-z0-9_-]*$``.

Adversarial cases live in ``test_path_traversal.py`` (NFR-004-003 focus).
This file covers the allowlist regex semantics and length cap.
"""

from __future__ import annotations

import pytest
from arvel.console._scaffold import (
    MAX_PROJECT_NAME_LENGTH,
    PROJECT_NAME_REGEX,
    InvalidProjectName,
    validate_project_name,
)


def test_regex_accepts_lowercase_alpha_start() -> None:
    """Regex itself is correct (covers the validation function and direct regex use)."""
    assert PROJECT_NAME_REGEX.fullmatch("my-app") is not None
    assert PROJECT_NAME_REGEX.fullmatch("a") is not None
    assert PROJECT_NAME_REGEX.fullmatch("blog_orm") is not None
    assert PROJECT_NAME_REGEX.fullmatch("my-app-v2") is not None


def test_regex_rejects_uppercase_letters() -> None:
    assert PROJECT_NAME_REGEX.fullmatch("MyApp") is None
    assert PROJECT_NAME_REGEX.fullmatch("my-App") is None


def test_regex_rejects_non_letter_start() -> None:
    assert PROJECT_NAME_REGEX.fullmatch("1numeric") is None
    assert PROJECT_NAME_REGEX.fullmatch("-leading-dash") is None
    assert PROJECT_NAME_REGEX.fullmatch("_leading-underscore") is None


def test_regex_rejects_dots_spaces_separators() -> None:
    assert PROJECT_NAME_REGEX.fullmatch("my.app") is None
    assert PROJECT_NAME_REGEX.fullmatch("my app") is None
    assert PROJECT_NAME_REGEX.fullmatch("my/app") is None
    assert PROJECT_NAME_REGEX.fullmatch("my\\app") is None


def test_max_length_is_64_chars() -> None:
    """Documented length cap matches the constant used in validation."""
    assert MAX_PROJECT_NAME_LENGTH == 64


@pytest.mark.parametrize(
    "name",
    ["my-app", "blog", "blog_orm", "a", "x" * 64, "v2-api-gateway"],
)
def test_validate_accepts_valid_names(name: str) -> None:
    assert validate_project_name(name) == name


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("", "empty"),
        ("My-App", "uppercase"),
        ("1blog", "starts with digit"),
        ("-app", "starts with dash"),
        ("my.app", "contains dot"),
        ("my app", "contains space"),
        ("my/app", "contains slash"),
        ("my\\app", "contains backslash"),
        ("x" * 65, "exceeds max length"),
    ],
)
def test_validate_rejects_invalid_names(name: str, reason: str) -> None:
    with pytest.raises(InvalidProjectName, match=r"."):
        validate_project_name(name)
    # Reason is included in the parametrize id only — referenced so the
    # arg isn't flagged as unused.
    assert isinstance(reason, str)


def test_invalid_project_name_is_value_error_subclass() -> None:
    """Generic ``except ValueError`` still catches our typed error."""
    assert issubclass(InvalidProjectName, ValueError)
