"""Mail configuration — Pydantic settings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class MailEncryption(StrEnum):
    TLS = "tls"
    SSL = "ssl"


class SmtpConfig(BaseSettings):
    """SMTP driver settings.

    ``password`` uses SecretStr so it never appears in repr/logs.
    """

    host: str = "localhost"
    port: int = 587
    username: str = ""
    password: SecretStr = SecretStr("")
    encryption: MailEncryption | None = MailEncryption.TLS

    model_config = {"env_prefix": "MAIL_SMTP_"}


class MailConfig(BaseSettings):
    """Top-level mail settings."""

    default: str = "log"
    from_address: str = "no-reply@example.com"
    from_name: str = "Arvel"

    model_config = {"env_prefix": "MAIL_"}


__all__ = ["MailConfig", "MailEncryption", "SmtpConfig"]
