"""env() strips wrapping quotes and leaves the inner value literal (round H2)."""

from __future__ import annotations

import pytest

from arvel.kernel.config import env


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"v"', "v"),
        ("'v'", "v"),
        ('"true"', "true"),  # quoted -> literal string, not coerced to bool
        ('""', ""),
        ("v", "v"),
    ],
)
def test_env_quote_stripping(monkeypatch: pytest.MonkeyPatch, raw: str, expected: str) -> None:
    monkeypatch.setenv("ARVEL_H2_TEST", raw)
    assert env("ARVEL_H2_TEST") == expected


def test_env_unquoted_literals_still_coerced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARVEL_H2_TEST", "true")
    assert env("ARVEL_H2_TEST") is True
    monkeypatch.setenv("ARVEL_H2_TEST", "null")
    assert env("ARVEL_H2_TEST") is None
