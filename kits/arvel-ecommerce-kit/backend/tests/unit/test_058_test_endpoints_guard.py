"""The test-only seed/refresh endpoints must be deny-by-default.

Only local/testing may reach them; development, staging, an unset APP_ENV,
and production all 404 so a reachable non-prod deployment can't be reseeded
by an anonymous caller.
"""

from __future__ import annotations

import pytest
from app.http.controllers.test import _guard_test_env
from arvel.http.exceptions import NotFoundException

pytestmark = [pytest.mark.unit, pytest.mark.security]


@pytest.mark.parametrize("value", ["local", "testing", "LOCAL", "Testing"])
def test_guard_allows_local_and_testing(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", value)
    _guard_test_env()  # must not raise


@pytest.mark.parametrize("value", ["production", "development", "staging", "prod", ""])
def test_guard_denies_everything_else(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", value)
    with pytest.raises(NotFoundException):
        _guard_test_env()


def test_guard_denies_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(NotFoundException):
        _guard_test_env()
