"""Default auth listener behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qs, urlsplit

from arvel.auth.email_verification_service import EmailVerificationService
from arvel.auth.events import PasswordResetRequested, Registered
from arvel.auth.listeners import (
    SendPasswordResetEmail,
    SendVerificationEmail,
    _build_reset_url,
    _set_ev_service,
)

if TYPE_CHECKING:
    import pytest


class _VerificationService:
    def issue(self, *, user_id: str, email: str) -> str:
        return f"{user_id}:{email}:signed"

    def build_url(self, *, base_url: str, signed: str) -> str:
        return f"{base_url}?signed={signed}"


async def test_verification_listener_returns_without_service_or_user() -> None:
    listener = SendVerificationEmail()
    event = Registered(user_id=None, email="user@example.com", occurred_at=datetime.now(tz=UTC))

    await listener.handle(event)


async def test_verification_listener_swallows_mail_failures() -> None:
    _set_ev_service(cast("EmailVerificationService", _VerificationService()))
    listener = SendVerificationEmail()
    event = Registered(user_id="u1", email="user@example.com", occurred_at=datetime.now(tz=UTC))

    await listener.handle(event)


async def test_password_reset_listener_returns_without_token() -> None:
    listener = SendPasswordResetEmail()
    event = PasswordResetRequested(
        user_id="u1",
        email="user@example.com",
        occurred_at=datetime.now(tz=UTC),
        reset_token=None,
    )

    await listener.handle(event)


async def test_password_reset_listener_swallows_mail_failures() -> None:
    listener = SendPasswordResetEmail()
    event = PasswordResetRequested(
        user_id="u1",
        email="user@example.com",
        occurred_at=datetime.now(tz=UTC),
        reset_token="reset-token",
    )

    await listener.handle(event)


def _patch_config(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    import importlib

    def fake_config(key: str, default: object = "") -> object:
        return values.get(key, default)

    # arvel/__init__ re-exports `config`, shadowing the submodule via getattr;
    # import_module returns the real module so the re-export gets patched.
    module = importlib.import_module("arvel.config")
    monkeypatch.setattr(module, "config", fake_config)


def test_build_reset_url_uses_configured_base(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_config(monkeypatch, {"auth.reset_page_url": "https://spa.example.com/reset"})

    url = _build_reset_url(token="tok-123", email="user@example.com")

    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://spa.example.com/reset"
    query = parse_qs(parts.query)
    assert query["token"] == ["tok-123"]
    assert query["email"] == ["user@example.com"]


def test_build_reset_url_falls_back_to_app_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_config(monkeypatch, {"auth.reset_page_url": "", "app.url": "https://shop.test"})

    url = _build_reset_url(token="t", email="a@b.com")

    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://shop.test/reset-password"


def test_build_reset_url_preserves_existing_query(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_config(monkeypatch, {"auth.reset_page_url": "https://spa.test/reset?lang=en"})

    url = _build_reset_url(token="t", email="a@b.com")

    query = parse_qs(urlsplit(url).query)
    assert query["lang"] == ["en"]
    assert query["token"] == ["t"]
    assert query["email"] == ["a@b.com"]
