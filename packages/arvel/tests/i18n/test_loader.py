"""Tests for PythonFileLoader."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from textwrap import dedent

import pytest


@pytest.fixture
def lang_path(tmp_path: Path) -> Iterator[Path]:
    base = tmp_path / "resources" / "lang" / "en"
    base.mkdir(parents=True)
    (tmp_path / "resources").joinpath("__init__.py").write_text("")
    (tmp_path / "resources" / "lang").joinpath("__init__.py").write_text("")
    base.joinpath("__init__.py").write_text("")
    base.joinpath("messages.py").write_text(
        dedent(
            """
            translations = {"hi": "hello"}
            """
        )
    )
    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    sys.path.remove(str(tmp_path))
    for mod in list(sys.modules):
        if mod.startswith("resources"):
            del sys.modules[mod]


def test_loads_translations_dict(lang_path: Path) -> None:
    from arvel.i18n.loader import PythonFileLoader

    loader = PythonFileLoader(base_path=lang_path)
    data = loader.load("en", "messages")

    assert data == {"hi": "hello"}


def test_missing_file_raises(lang_path: Path) -> None:
    from arvel.i18n.exceptions import TranslationFileMissingError
    from arvel.i18n.loader import PythonFileLoader

    loader = PythonFileLoader(base_path=lang_path)

    with pytest.raises(TranslationFileMissingError):
        loader.load("en", "nonexistent")


def test_malformed_file_raises(lang_path: Path) -> None:
    """File exists but does not export translations: dict."""
    from arvel.i18n.exceptions import TranslationFileMalformedError
    from arvel.i18n.loader import PythonFileLoader

    bad = lang_path / "resources" / "lang" / "en" / "bad.py"
    bad.write_text("# no translations export\nfoo = 1\n")

    loader = PythonFileLoader(base_path=lang_path)

    with pytest.raises(TranslationFileMalformedError):
        loader.load("en", "bad")


def test_traversal_locale_does_not_execute_outside_file(tmp_path: Path) -> None:
    """A ``..`` locale must not escape resources/lang to exec a planted file."""
    from arvel.i18n.exceptions import TranslationFileMissingError
    from arvel.i18n.loader import PythonFileLoader

    base = tmp_path / "app"
    (base / "resources" / "lang").mkdir(parents=True)
    # Planted next to the app root, reachable via ../ from resources/lang.
    evil = tmp_path / "evil.py"
    evil.write_text("raise RuntimeError('lang loader executed an outside file')\n")

    loader = PythonFileLoader(base_path=base)
    with pytest.raises(TranslationFileMissingError):
        loader.load("../../..", "evil")


def test_json_loader_rejects_separator_in_locale(tmp_path: Path) -> None:
    from arvel.i18n.exceptions import TranslationFileMissingError
    from arvel.i18n.loader import JsonFileLoader

    loader = JsonFileLoader(base_path=tmp_path)
    with pytest.raises(TranslationFileMissingError):
        loader.load("../secrets", "messages")
