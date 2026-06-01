"""Tests for the request-aware t() helper.
Tests are written RED — t() is not yet added to arvel.i18n.helpers.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from starlette.requests import Request

if TYPE_CHECKING:
    from arvel.i18n import Translator

# fixtures


@pytest.fixture
def translator(tmp_path: Path) -> Translator:
    """Return a Translator bound with a tiny en/es catalog."""
    from arvel.i18n import JsonFileLoader, Translator

    # JsonFileLoader expects base_path / "resources" / "lang" / locale / namespace.json
    lang_root = tmp_path / "resources" / "lang"
    (lang_root / "en").mkdir(parents=True)
    (lang_root / "es").mkdir(parents=True)

    (lang_root / "en" / "messages.json").write_text(
        '{"greeting": "Hello :name", "plain": "English"}'
    )
    (lang_root / "es" / "messages.json").write_text(
        '{"greeting": "Hola :name", "plain": "Español"}'
    )

    loader = JsonFileLoader(tmp_path)
    return Translator(loader=loader, default_locale="en", fallback_locale="en")


@pytest.fixture
def bound_translator(translator: Translator) -> Generator[Translator]:
    from arvel.i18n.helpers import bind_translator, unbind_translator

    bind_translator(translator)
    yield translator
    unbind_translator()


def _fake_request(locale: str | None = None) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    if locale is not None:
        scope["state"] = {"locale": locale}
    return Request(scope)


#: t() uses request.state.locale


def test_t_uses_request_locale(bound_translator: Translator) -> None:
    from arvel.i18n import t

    request = _fake_request(locale="es")
    result = t(request, "messages.plain")
    assert result == "Español"


def test_t_uses_english_when_locale_is_en(bound_translator: Translator) -> None:
    from arvel.i18n import t

    request = _fake_request(locale="en")
    assert t(request, "messages.plain") == "English"


def test_t_performs_replacements(bound_translator: Translator) -> None:
    from arvel.i18n import t

    request = _fake_request(locale="es")
    assert t(request, "messages.greeting", name="Alice") == "Hola Alice"


#: t() falls back gracefully when locale absent


def test_t_falls_back_when_state_has_no_locale(bound_translator: Translator) -> None:
    from arvel.i18n import t

    request = _fake_request(locale=None)  # no state.locale
    # Must not raise; returns translation in default locale
    result = t(request, "messages.plain")
    assert result == "English"


def test_t_importable_from_arvel_i18n() -> None:
    """t must be exported from arvel.i18n top-level."""
    from arvel.i18n import t

    assert callable(t)


# Security: t() must not surface raw exceptions


def test_t_missing_key_returns_key_not_exception(bound_translator: Translator) -> None:
    from arvel.i18n import t

    request = _fake_request(locale="en")
    result = t(request, "nonexistent.key")
    # Per framework convention: missing key returns the key itself
    assert "exception" not in result.lower()
    assert "error" not in result.lower()
