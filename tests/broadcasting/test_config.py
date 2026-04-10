"""Tests for BroadcastSettings — FR-003.

FR-003: BroadcastSettings with BROADCAST_ env prefix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


class TestBroadcastSettings:
    """FR-003: Config uses BROADCAST_ prefix and supports driver selection."""

    def test_default_driver_is_null(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BROADCAST_DRIVER", raising=False)
        from arvel.broadcasting.config import BroadcastSettings

        settings = BroadcastSettings()
        assert settings.driver == "null"

    def test_driver_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BROADCAST_DRIVER", "memory")
        from arvel.broadcasting.config import BroadcastSettings

        settings = BroadcastSettings()
        assert settings.driver == "memory"

    def test_auth_endpoint_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BROADCAST_AUTH_ENDPOINT", raising=False)
        from arvel.broadcasting.config import BroadcastSettings

        settings = BroadcastSettings()
        assert settings.auth_endpoint == "/broadcasting/auth"
