"""Tests for Sentry integration — FR-036 to FR-039, SEC-006."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from arvel.observability import sentry as sentry_module
from arvel.observability.config import ObservabilitySettings

if TYPE_CHECKING:
    import pytest


class TestConfigureSentry:
    def test_noop_when_dsn_empty(self) -> None:
        """FR-037: when SENTRY_DSN is empty, Sentry not initialized."""
        settings = ObservabilitySettings(sentry_dsn="")
        result = sentry_module.configure_sentry(settings)
        assert result is None or result is False

    def test_noop_when_sentry_not_installed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FR-037: when sentry-sdk not installed, no import error."""
        settings = ObservabilitySettings(sentry_dsn="https://key@sentry.io/123")
        monkeypatch.setattr(sentry_module, "_HAS_SENTRY", False)
        result = sentry_module.configure_sentry(settings)
        assert result is False

    def test_configure_sentry_uses_mocked_sdk(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No real Sentry SDK/network side effects in tests."""
        settings = ObservabilitySettings(
            sentry_dsn="https://key@sentry.io/123",
            sentry_traces_sample_rate=0.5,
        )
        captured: dict[str, object] = {}

        def fake_init(
            *,
            dsn: str,
            traces_sample_rate: float,
            send_default_pii: bool,
        ) -> None:
            captured["dsn"] = dsn
            captured["traces_sample_rate"] = traces_sample_rate
            captured["send_default_pii"] = send_default_pii

        monkeypatch.setattr(sentry_module, "_HAS_SENTRY", True)
        monkeypatch.setattr(
            sentry_module,
            "sentry_sdk",
            SimpleNamespace(init=fake_init),
            raising=False,
        )

        result = sentry_module.configure_sentry(settings)
        assert result is True
        assert captured["dsn"] == "https://key@sentry.io/123"
        assert captured["traces_sample_rate"] == 0.5
        assert captured["send_default_pii"] is False
