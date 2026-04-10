"""Tests for SecuritySettings — defaults and env overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.security.config import SecuritySettings

if TYPE_CHECKING:
    import pytest


class TestSecuritySettingsDefaults:
    def test_default_hash_driver(self, clean_env: None) -> None:
        settings = SecuritySettings()
        assert settings.hash_driver == "bcrypt"

    def test_default_bcrypt_rounds(self, clean_env: None) -> None:
        settings = SecuritySettings()
        assert settings.bcrypt_rounds == 12

    def test_default_jwt_algorithm(self, clean_env: None) -> None:
        settings = SecuritySettings()
        assert settings.jwt_algorithm == "HS256"

    def test_default_csrf_enabled(self, clean_env: None) -> None:
        settings = SecuritySettings()
        assert settings.csrf_enabled is True

    def test_default_audit_enabled(self, clean_env: None) -> None:
        settings = SecuritySettings()
        assert settings.audit_enabled is True


class TestSecuritySettingsEnvOverride:
    def test_override_hash_driver(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECURITY_HASH_DRIVER", "argon2")
        settings = SecuritySettings()
        assert settings.hash_driver == "argon2"

    def test_override_jwt_algorithm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECURITY_JWT_ALGORITHM", "RS256")
        settings = SecuritySettings()
        assert settings.jwt_algorithm == "RS256"

    def test_env_prefix_is_security(self) -> None:
        prefix = SecuritySettings.model_config.get("env_prefix", "")
        assert prefix == "SECURITY_"

    def test_extra_fields_ignored(self) -> None:
        settings = SecuritySettings.model_validate({"unknown_field": "should not fail"})
        assert not hasattr(settings, "unknown_field")
