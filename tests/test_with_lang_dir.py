"""`Application.configure(...).with_lang_dir(...)` — loads the app's translations from a custom
directory (e.g. `resources/lang`, the pre--9 convention) instead of the default
`{base_path}/lang`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from arvel.kernel.application import Application
from arvel.kernel.discovery import bootstrap_providers, clear_cache
from arvel.kernel.globals import set_application
from arvel.support.facades import Lang


def _write_lang_file(directory: Path) -> None:
    en = directory / "en"
    en.mkdir(parents=True)
    (en / "messages.json").write_text(json.dumps({"greeting": "Hello, {name}"}))


def test_with_lang_dir_loads_translations_from_the_custom_directory(tmp_path: Path) -> None:
    lang_dir = tmp_path / "resources" / "lang"
    _write_lang_file(lang_dir)

    clear_cache()
    app = Application.configure(str(tmp_path)).with_lang_dir(lang_dir).create()
    bootstrap_providers(app)
    asyncio.run(app.boot())
    set_application(app)
    try:
        assert app.lang_dir == str(lang_dir)
        assert Lang.get("messages.greeting", {"name": "Ada"}) == "Hello, Ada"
    finally:
        set_application(None)


def test_default_lang_dir_is_base_path_lang_when_not_overridden(tmp_path: Path) -> None:
    _write_lang_file(tmp_path / "lang")

    clear_cache()
    app = Application.configure(str(tmp_path)).create()
    bootstrap_providers(app)
    asyncio.run(app.boot())
    set_application(app)
    try:
        assert app.lang_dir is None
        assert Lang.get("messages.greeting", {"name": "Ada"}) == "Hello, Ada"
    finally:
        set_application(None)
