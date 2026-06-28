"""Lang facade / translator binding: LocalizationServiceProvider binds "translator" so the
Lang facade resolves (previously unbound — Lang.get(...) raised BindingResolutionError)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from arvel.kernel.application import Application
from arvel.kernel.discovery import bootstrap_providers, clear_cache
from arvel.kernel.globals import set_application
from arvel.localization import Translator
from arvel.support.facades import Lang


@pytest.fixture
def booted_app() -> Iterator[Application]:
    clear_cache()
    app = Application.configure().create()
    bootstrap_providers(app)
    asyncio.run(app.boot())
    set_application(app)
    try:
        yield app
    finally:
        set_application(None)


def test_translator_is_bound(booted_app: Application) -> None:
    assert booted_app.bound("translator")
    assert isinstance(booted_app.make("translator"), Translator)


def test_lang_facade_resolves_and_translates(booted_app: Application) -> None:
    booted_app.make("translator").add("en", {"greeting": "Hello, {name}"})
    assert Lang.get("greeting", {"name": "Ada"}) == "Hello, Ada"
    assert Lang.get("missing.key") == "missing.key"  # falls back to the key, no error
