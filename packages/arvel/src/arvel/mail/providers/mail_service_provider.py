"""MailServiceProvider — registers Mailer and Mail facade.

Driver selection follows Laravel's priority order:

1. ``config/mail.py`` (Laravel-shaped config file, read via
 :func:`arvel.config.lookup`) — used when the application ships a
 ``config/mail.py`` module.
2. ``MAIL_*`` / ``MAIL_SMTP_*`` env vars via :class:`MailConfig` (Pydantic
 ``BaseSettings``) — used when no config file is present.

This means any Arvel app that provides ``config/mail.py`` gets full
mail wiring without writing a custom provider.
"""

from __future__ import annotations

from typing import Any, cast

from arvel.mail.config import MailConfig
from arvel.mail.mailer import Mailer
from arvel.providers.service_provider import ServiceProvider


class MailServiceProvider(ServiceProvider):
    """Registers Mailer singleton and wires the Mail facade."""

    def register(self) -> None:
        mailer = _build_mailer()
        self.container.instance(Mailer, mailer)

    async def boot(self) -> None:
        from arvel.facades.mail import Mail

        mailer = self.container.make(Mailer)
        Mail.bind(mailer)


def _build_mailer() -> Mailer:
    """Resolve the configured driver and return a :class:`Mailer`.

    Prefers config-file values over env vars so apps that follow the
    Laravel config-file convention don't need a custom provider.
    """
    try:
        from arvel.config import lookup as _lookup

        driver_name = str(_lookup("mail.default") or "log").lower()
        return _build_mailer_from_config(driver_name)
    except Exception:  # noqa: BLE001 — config not wired yet (e.g. tests without config bootstrap)
        return _build_mailer_from_env()


def _build_mailer_from_config(driver_name: str) -> Mailer:
    """Build :class:`Mailer` from ``config/mail.py`` values."""
    try:
        from pydantic import SecretStr

        from arvel.config import lookup
        from arvel.mail.config import MailEncryption, SmtpConfig

        from_address = str(lookup("mail.from_address") or "")
        from_name = str(lookup("mail.from_name") or "")
        mail_config = MailConfig(
            default=driver_name,
            from_address=from_address,
            from_name=from_name,
        )

        driver: Any
        if driver_name == "smtp":
            smtp_settings: dict[str, Any] = {}
            raw = lookup("mail.mailers.smtp")
            if isinstance(raw, dict):
                smtp_settings = cast("dict[str, Any]", raw)
            encryption_raw = smtp_settings.get("encryption")
            encryption: MailEncryption | None = None
            if isinstance(encryption_raw, str) and encryption_raw:
                encryption = MailEncryption(encryption_raw.lower())
            smtp_config = SmtpConfig(
                host=str(smtp_settings.get("host") or "localhost"),
                port=int(smtp_settings.get("port") or 1025),
                username=str(smtp_settings.get("username") or ""),
                password=SecretStr(str(smtp_settings.get("password") or "")),
                encryption=encryption,
            )
            from arvel.mail.drivers.smtp import SmtpMailDriver

            driver = SmtpMailDriver(smtp_config)
        elif driver_name == "array":
            from arvel.mail.drivers.array import ArrayMailDriver

            driver = ArrayMailDriver()
        else:
            from arvel.mail.drivers.log import LogMailDriver

            driver = LogMailDriver()

        return Mailer(default_driver=driver, config=mail_config)
    except Exception:  # noqa: BLE001
        return _build_mailer_from_env()


def _build_mailer_from_env() -> Mailer:
    """Build :class:`Mailer` from ``MAIL_*`` env vars (Pydantic BaseSettings fallback)."""
    config = MailConfig()
    driver_name = config.default
    driver: Any

    if driver_name == "array":
        from arvel.mail.drivers.array import ArrayMailDriver

        driver = ArrayMailDriver()
    elif driver_name == "smtp":
        from arvel.mail.config import SmtpConfig
        from arvel.mail.drivers.smtp import SmtpMailDriver

        driver = SmtpMailDriver(SmtpConfig())
    else:
        from arvel.mail.drivers.log import LogMailDriver

        driver = LogMailDriver()

    return Mailer(default_driver=driver, config=config)


__all__ = ["MailServiceProvider"]
