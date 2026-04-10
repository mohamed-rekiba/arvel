"""Mail configuration — typed settings with MAIL_ env prefix."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.foundation.config import ModuleSettings


class MailSettings(ModuleSettings):
    """Mail driver configuration.

    All values can be overridden via environment variables prefixed with ``MAIL_``.
    """

    model_config = SettingsConfigDict(env_prefix="MAIL_", extra="ignore")

    driver: str = "log"
    from_address: str = "noreply@localhost"
    from_name: str = "Arvel"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_use_tls: bool = True
    template_dir: str = "templates/mail"


settings_class = MailSettings
