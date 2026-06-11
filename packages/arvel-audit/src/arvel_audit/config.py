"""Audit configuration via ``AUDIT_*`` environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuditConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    enabled: bool = Field(default=True, alias="AUDIT_ENABLED")
    encrypt_values: bool = Field(default=False, alias="AUDIT_ENCRYPT_VALUES")


# Process-wide active config. The provider sets it to the same instance it binds
# to the container, so observers read one object (no per-write .env reload) and
# toggling `audit_config().enabled = False` takes effect immediately.
class _ConfigHolder:
    active: AuditConfig | None = None


def set_audit_config(config: AuditConfig) -> None:
    """Make *config* the active audit config that observers consult."""
    _ConfigHolder.active = config


def audit_config() -> AuditConfig:
    """Return the active audit config, env-loading a default on first use."""
    if _ConfigHolder.active is None:
        _ConfigHolder.active = AuditConfig()
    return _ConfigHolder.active


__all__ = ["AuditConfig", "audit_config", "set_audit_config"]
