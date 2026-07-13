"""C9 — translation file loaders + LocaleMiddleware."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import LocaleMiddleware
from arvel.localization import Translator, current_locale, load_translations


def _seed_lang(root: Path) -> Path:
    lang = root / "lang"
    lang.mkdir()
    (lang / "en.json").write_text(json.dumps({"hello": "Hello"}))
    (lang / "es.json").write_text(json.dumps({"hello": "Hola"}))
    (lang / "fr").mkdir()
    (lang / "fr" / "messages.json").write_text(json.dumps({"welcome": "Bienvenue"}))
    return lang


def test_load_translations_flat_and_grouped(tmp_path: Path) -> None:
    data = load_translations(_seed_lang(tmp_path))
    assert data["en"]["hello"] == "Hello"
    assert data["es"]["hello"] == "Hola"
    assert data["fr"]["messages"]["welcome"] == "Bienvenue"


def test_translator_load_and_lookup(tmp_path: Path) -> None:
    translator = Translator().load(_seed_lang(tmp_path))
    assert translator.get("hello", locale="es") == "Hola"
    assert translator.get("messages.welcome", locale="fr") == "Bienvenue"


def test_locale_middleware_sets_locale_from_header() -> None:
    def _handler(request: Any) -> dict[str, str]:
        return {"locale": current_locale.get()}

    kernel = HttpKernel()
    kernel.global_middleware = [LocaleMiddleware]
    kernel.get("/", _handler)
    with TestClient(kernel.build()) as client:
        assert client.get("/", headers={"accept-language": "es-ES,es;q=0.9"}).json() == {
            "locale": "es"
        }
