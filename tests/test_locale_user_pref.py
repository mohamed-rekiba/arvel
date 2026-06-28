"""HTTP/L10n (doc 21) — LocaleMiddleware prefers the user's locale over Accept-Language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arvel.auth import current_user
from arvel.http.middleware import LocaleMiddleware
from arvel.localization import current_locale


@dataclass
class Req:
    headers: dict[str, str]

    def header(self, name: str) -> str | None:
        return self.headers.get(name)


@dataclass
class User:
    locale: str | None = None


async def _capture(_req: Any) -> str:
    return current_locale.get()


async def test_user_pref_wins_over_header() -> None:
    token = current_user.set(User(locale="fr"))
    try:
        result = await LocaleMiddleware().handle(Req({"accept-language": "de-DE,de"}), _capture)
        assert result == "fr"
    finally:
        current_user.reset(token)


async def test_falls_back_to_header_when_user_has_no_locale() -> None:
    token = current_user.set(User(locale=None))
    try:
        result = await LocaleMiddleware().handle(Req({"accept-language": "es-ES,es"}), _capture)
        assert result == "es"
    finally:
        current_user.reset(token)


async def test_header_used_when_no_user() -> None:
    result = await LocaleMiddleware().handle(Req({"accept-language": "ja"}), _capture)
    assert result == "ja"


async def test_passthrough_when_nothing_resolves() -> None:
    before = current_locale.get()
    result = await LocaleMiddleware().handle(Req({}), _capture)
    assert result == before  # locale unchanged
