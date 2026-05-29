"""NFR-001-004: Secret* types never leak in error paths."""

from __future__ import annotations

import os

import pytest
from arvel.support.env import EnvCoercionError, env
from pydantic import SecretStr


def test_secretstr_repr_hides_value() -> None:
    s = SecretStr("super-sensitive")
    assert "super-sensitive" not in repr(s)
    assert "super-sensitive" not in str(s)


def test_config_section_with_secret_does_not_print_secret() -> None:
    from arvel.config import ArvelSettings

    class Secrets(ArvelSettings):
        api_key: SecretStr = SecretStr("hunter2")

    s = Secrets()
    assert "hunter2" not in repr(s)
    assert "hunter2" not in str(s)


@pytest.mark.parametrize(
    ("default", "raw"),
    [(0, "sk-very-secret-token-abc123"), (0.0, "secret-float"), (False, "secret-bool")],
)
def test_env_coercion_error_does_not_leak_raw_value(
    default: object, raw: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 4b: env() coercion errors must NOT echo the raw env value.

    Apps routinely log exceptions; raw env values are often secrets
    (API keys, passwords, tokens). See SAD-001 §4 / OWASP A09.
    """
    monkeypatch.setenv("ARVEL_SECRET_FOR_TEST", raw)
    with pytest.raises(EnvCoercionError) as excinfo:
        env("ARVEL_SECRET_FOR_TEST", default)  # type: ignore[call-overload]
    msg = str(excinfo.value)
    assert raw not in msg, f"raw env value leaked into error message: {msg!r}"
    assert "ARVEL_SECRET_FOR_TEST" in msg, "key name should be present for debugging"


def test_env_required_missing_does_not_include_environ_state() -> None:
    """The LookupError raised by env(..., required=True) must not enumerate other env vars."""
    os.environ.pop("DEFINITELY_NOT_SET_ARVEL", None)
    with pytest.raises(LookupError) as excinfo:
        env("DEFINITELY_NOT_SET_ARVEL", required=True)
    msg = str(excinfo.value)
    # Sanity: any of these would indicate the env dict was iterated/serialized
    assert "PATH" not in msg
    assert "HOME" not in msg
    assert "DEFINITELY_NOT_SET_ARVEL" in msg
