"""MailServiceProvider builder branches."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import cast

import pytest
from arvel.mail.drivers.array import ArrayMailDriver
from arvel.mail.drivers.log import LogMailDriver
from arvel.mail.drivers.smtp import SmtpMailDriver
from arvel.mail.mailer import Mailer
from arvel.mail.providers import mail_service_provider as provider_module

config_module = importlib.import_module("arvel.config")


def _build_from_config(driver: str) -> Mailer:
    build = cast(
        "Callable[[str], Mailer]",
        object.__getattribute__(provider_module, "_build_mailer_from_config"),
    )
    return build(driver)


def _build_from_env() -> Mailer:
    build = cast(
        "Callable[[], Mailer]",
        object.__getattribute__(provider_module, "_build_mailer_from_env"),
    )
    return build()


def test_mail_provider_builds_array_and_log_from_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def lookup(key: str) -> object:
        values: dict[str, object] = {
            "mail.from_address": "team@example.test",
            "mail.from_name": "Team",
        }
        return values.get(key)

    monkeypatch.setattr(config_module, "lookup", lookup)

    array_mailer = _build_from_config("array")
    log_mailer = _build_from_config("log")

    assert isinstance(array_mailer.current_driver, ArrayMailDriver)
    assert isinstance(log_mailer.current_driver, LogMailDriver)


def test_mail_provider_builds_smtp_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    def lookup(key: str) -> object:
        values: dict[str, object] = {
            "mail.from_address": "team@example.test",
            "mail.from_name": "Team",
            "mail.mailers.smtp": {
                "host": "smtp.example.test",
                "port": 2525,
                "username": "user",
                "password": "secret",
                "encryption": "ssl",
            },
        }
        return values.get(key)

    monkeypatch.setattr(config_module, "lookup", lookup)

    mailer = _build_from_config("smtp")

    assert isinstance(mailer.current_driver, SmtpMailDriver)


def test_mail_provider_falls_back_to_env_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    def lookup(key: str) -> object:
        raise RuntimeError

    monkeypatch.setattr(config_module, "lookup", lookup)

    mailer = _build_from_config("smtp")

    assert isinstance(mailer.current_driver, LogMailDriver)


def test_mail_provider_builds_array_and_smtp_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAIL_DEFAULT", "array")
    assert isinstance(_build_from_env().current_driver, ArrayMailDriver)

    monkeypatch.setenv("MAIL_DEFAULT", "smtp")
    assert isinstance(_build_from_env().current_driver, SmtpMailDriver)
