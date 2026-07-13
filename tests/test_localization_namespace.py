"""Localization (doc 21) — namespaced package translations resolve as ``pkg::group.key``."""

from __future__ import annotations

import json
from pathlib import Path

from arvel.localization import Translator, current_locale


def _pkg_lang(tmp_path: Path) -> Path:
    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "fr").mkdir(parents=True)
    (lang / "en" / "messages.json").write_text(json.dumps({"welcome": "Welcome to {app}"}))
    (lang / "fr" / "messages.json").write_text(json.dumps({"welcome": "Bienvenue sur {app}"}))
    return lang


def test_namespaced_lookup_with_replacement(tmp_path: Path) -> None:
    t = Translator(fallback="en").add_namespace("billing", _pkg_lang(tmp_path))
    current_locale.set("fr")
    try:
        assert t.get("billing::messages.welcome", {"app": "Arvel"}) == "Bienvenue sur Arvel"
    finally:
        current_locale.set("en")


def test_namespace_falls_back_to_fallback_locale(tmp_path: Path) -> None:
    t = Translator(fallback="en").add_namespace("billing", _pkg_lang(tmp_path))
    # de is missing -> falls back to en within the same namespace
    assert t.get("billing::messages.welcome", {"app": "X"}, locale="de") == "Welcome to X"


def test_unknown_namespace_returns_key(tmp_path: Path) -> None:
    t = Translator(fallback="en")
    assert t.get("nope::messages.welcome") == "nope::messages.welcome"


def test_namespace_does_not_leak_into_app_keys(tmp_path: Path) -> None:
    t = Translator(fallback="en").add_namespace("billing", _pkg_lang(tmp_path))
    # the bare app key is NOT resolvable without the namespace prefix
    assert t.get("messages.welcome") == "messages.welcome"
