"""Translatable model attributes — a per-locale jsonb value read as the current locale's string
(Spatie HasTranslations parity)."""

from __future__ import annotations

from typing import ClassVar

import pytest

from arvel import Model
from arvel.localization import HasTranslations, Translatable, current_locale


class _Post(HasTranslations, Model):
    __fields__: ClassVar[dict[str, type]] = {"title": str}
    __fillable__: ClassVar[list[str]] = ["title"]
    __casts__: ClassVar[dict[str, object]] = {"title": Translatable()}


@pytest.fixture(autouse=True)
def _reset_locale():  # type: ignore[no-untyped-def]
    token = current_locale.set("en")
    yield
    current_locale.reset(token)


def test_reads_the_current_locale_value() -> None:
    post = _Post(title={"en": "Hello", "fr": "Bonjour"})
    assert post.title == "Hello"
    current_locale.set("fr")
    assert post.title == "Bonjour"


def test_falls_back_to_the_default_locale() -> None:
    post = _Post(title={"en": "Hello"})
    current_locale.set("de")  # no German → fall back to en
    assert post.title == "Hello"


def test_set_translation_merges_and_helpers_read() -> None:
    post = _Post(title={"en": "Hello"})
    post.set_translation("title", "fr", "Bonjour")
    assert post.get_translation("title", "fr") == "Bonjour"
    assert post.get_translation("title", "en") == "Hello"
    assert post.translations("title") == {"en": "Hello", "fr": "Bonjour"}


def test_assigning_a_bare_string_sets_the_current_locale() -> None:
    post = _Post(title={"en": "Hello", "fr": "Bonjour"})
    current_locale.set("fr")
    post.title = "Salut"  # sets only the current (fr) translation
    assert post.translations("title") == {"en": "Hello", "fr": "Salut"}


def test_load_and_edge_cases() -> None:
    from arvel.localization.translatable import Translatable, _load

    assert _load({"en": "x"}) == {"en": "x"}  # dict (Postgres jsonb) path
    assert _load(None) == {}
    assert _load("") == {}

    cast = Translatable(fallback="en")
    assert cast.get(None, "title", None, {}) is None  # no data → None
    current_locale.set("de")  # no de, no en → first available value
    assert cast.get(None, "title", {"es": "Hola"}, {}) == "Hola"
