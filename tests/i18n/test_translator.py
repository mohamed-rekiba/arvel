"""Tests for i18n — Story 2."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from arvel.i18n import Translator

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def lang_dir(tmp_path: Path) -> Path:
    en_dir = tmp_path / "users" / "lang"
    en_dir.mkdir(parents=True)

    en_file = en_dir / "en.json"
    en_file.write_text(json.dumps({"welcome": "Welcome, {name}!", "goodbye": "Goodbye"}))

    fr_dir = tmp_path / "users" / "lang"
    fr_file = fr_dir / "fr.json"
    fr_file.write_text(json.dumps({"welcome": "Bienvenue, {name} !"}))

    return tmp_path


@pytest.fixture
def translator(lang_dir: Path) -> Translator:
    t = Translator(default_locale="en", fallback_locale="en")
    t.load_module("users", lang_dir / "users" / "lang")
    return t


class TestTranslator:
    def test_basic_translation(self, translator: Translator) -> None:
        result = translator.get("users.welcome", locale="en", name="Alice")
        assert result == "Welcome, Alice!"

    def test_fallback_to_default(self, translator: Translator) -> None:
        result = translator.get("users.goodbye", locale="fr")
        assert result == "Goodbye"

    def test_missing_key_returns_key(self, translator: Translator) -> None:
        result = translator.get("users.unknown")
        assert result == "users.unknown"

    def test_french_translation(self, translator: Translator) -> None:
        result = translator.get("users.welcome", locale="fr", name="Alice")
        assert result == "Bienvenue, Alice !"

    def test_module_not_loaded(self, translator: Translator) -> None:
        result = translator.get("orders.total")
        assert result == "orders.total"
