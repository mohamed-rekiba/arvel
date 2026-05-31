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


__all__ = ["AuditConfig"]
