"""Localization (doc 03/21) — boot() wires load_translations_from namespaces into the translator."""

from __future__ import annotations

import json
from pathlib import Path

from arvel.kernel import Application
from arvel.localization import Translator


def _pkg_lang(tmp_path: Path) -> Path:
    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "en" / "messages.json").write_text(json.dumps({"hello": "Hi from billing"}))
    return lang


async def test_boot_registers_translation_namespaces(tmp_path: Path) -> None:
    app = Application()
    translator = Translator(fallback="en")
    app.instance("translator", translator)
    app.translation_namespaces["billing"] = str(
        _pkg_lang(tmp_path)
    )  # as load_translations_from does

    await app.boot()

    assert translator.get("billing::messages.hello") == "Hi from billing"


async def test_boot_without_translator_is_noop(tmp_path: Path) -> None:
    app = Application()
    app.translation_namespaces["billing"] = str(_pkg_lang(tmp_path))
    await app.boot()  # no translator bound -> must not raise
    assert app.booted
