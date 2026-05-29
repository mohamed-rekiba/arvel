"""FR-001-005: env() typed wrapper."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def clean_env() -> Iterator[None]:
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


def test_env_returns_none_when_missing_and_no_default(clean_env: None) -> None:
    from arvel.support.env import env

    os.environ.pop("ARVEL_TEST_KEY", None)
    assert env("ARVEL_TEST_KEY") is None


def test_env_returns_string_when_set(clean_env: None) -> None:
    from arvel.support.env import env

    os.environ["ARVEL_TEST_KEY"] = "hello"
    assert env("ARVEL_TEST_KEY") == "hello"


@pytest.mark.parametrize(
    ("raw", "default", "expected"),
    [
        ("42", 0, 42),
        ("3.14", 0.0, 3.14),
        ("true", False, True),
        ("FALSE", True, False),
        ("yes", False, True),
        ("no", True, False),
        ("on", False, True),
        ("off", True, False),
        ("1", False, True),
        ("0", True, False),
        ("a,b,c", [], ["a", "b", "c"]),
    ],
)
def test_env_coerces_to_default_type(
    clean_env: None,
    raw: str,
    default: object,
    expected: object,
) -> None:
    from arvel.support.env import env

    os.environ["ARVEL_TEST_KEY"] = raw
    assert env("ARVEL_TEST_KEY", default) == expected  # type: ignore[call-overload]


def test_env_default_returned_when_missing(clean_env: None) -> None:
    from arvel.support.env import env

    os.environ.pop("ARVEL_TEST_KEY", None)
    assert env("ARVEL_TEST_KEY", "fallback") == "fallback"
    assert env("ARVEL_TEST_KEY", 7) == 7


def test_env_bad_bool_raises_coercion_error(clean_env: None) -> None:
    from arvel.support.env import EnvCoercionError, env

    os.environ["ARVEL_TEST_KEY"] = "maybe"
    with pytest.raises(EnvCoercionError):
        env("ARVEL_TEST_KEY", False)


def test_env_required_missing_raises(clean_env: None) -> None:
    from arvel.support.env import env

    os.environ.pop("ARVEL_TEST_KEY", None)
    with pytest.raises(LookupError, match="ARVEL_TEST_KEY"):
        env("ARVEL_TEST_KEY", required=True)


def test_env_required_present_returns_str(clean_env: None) -> None:
    from arvel.support.env import env

    os.environ["ARVEL_TEST_KEY"] = "x"
    assert env("ARVEL_TEST_KEY", required=True) == "x"
