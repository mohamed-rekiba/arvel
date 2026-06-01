"""Tests for :class:`arvel.i18n.JsonFileLoader`.
The driver supports two layouts:

- ``resources/lang/{locale}/{namespace}.json`` — one file per namespace.
- ``resources/lang/{locale}.json`` — one file per locale, namespaces are
  top-level keys. This is the layout uses so a single file
  serves both backend (this loader) and frontend (Vue I18n) consumers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from arvel.i18n.exceptions import (
    TranslationFileMalformedError,
    TranslationFileMissingError,
)
from arvel.i18n.loader import JsonFileLoader


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_loads_nested_layout(tmp_path: Path) -> None:
    """Reads ``resources/lang/{locale}/{namespace}.json``."""
    target = tmp_path / "resources" / "lang" / "en" / "messages.json"
    _write_json(target, {"hi": "hello", "bye": "see you"})

    loader = JsonFileLoader(base_path=tmp_path)
    data = loader.load("en", "messages")

    assert data == {"hi": "hello", "bye": "see you"}


def test_loads_single_file_layout(tmp_path: Path) -> None:
    """Reads ``resources/lang/{locale}.json`` with namespaces as keys."""
    target = tmp_path / "resources" / "lang" / "es.json"
    _write_json(
        target,
        {
            "messages": {"hi": "hola"},
            "auth": {"login": "iniciar sesión"},
        },
    )

    loader = JsonFileLoader(base_path=tmp_path)

    assert loader.load("es", "messages") == {"hi": "hola"}
    assert loader.load("es", "auth") == {"login": "iniciar sesión"}


def test_nested_layout_takes_precedence_over_single_file(tmp_path: Path) -> None:
    """When both layouts exist, the per-namespace file wins."""
    nested = tmp_path / "resources" / "lang" / "en" / "messages.json"
    single = tmp_path / "resources" / "lang" / "en.json"
    _write_json(nested, {"hi": "from nested"})
    _write_json(single, {"messages": {"hi": "from single"}})

    loader = JsonFileLoader(base_path=tmp_path)

    assert loader.load("en", "messages") == {"hi": "from nested"}


def test_missing_locale_raises(tmp_path: Path) -> None:
    """Neither layout exists → ``TranslationFileMissingError``."""
    loader = JsonFileLoader(base_path=tmp_path)

    with pytest.raises(TranslationFileMissingError):
        loader.load("en", "messages")


def test_missing_namespace_in_single_file_raises(tmp_path: Path) -> None:
    """Single-file layout, locale exists, but the namespace key is absent."""
    target = tmp_path / "resources" / "lang" / "en.json"
    _write_json(target, {"messages": {"hi": "hello"}})

    loader = JsonFileLoader(base_path=tmp_path)

    with pytest.raises(TranslationFileMissingError):
        loader.load("en", "auth")


def test_invalid_json_raises_malformed(tmp_path: Path) -> None:
    """Syntactically invalid JSON → ``TranslationFileMalformedError``."""
    target = tmp_path / "resources" / "lang" / "en" / "messages.json"
    target.parent.mkdir(parents=True)
    target.write_text("{ this is not json", encoding="utf-8")

    loader = JsonFileLoader(base_path=tmp_path)

    with pytest.raises(TranslationFileMalformedError):
        loader.load("en", "messages")


def test_non_dict_root_in_single_file_raises(tmp_path: Path) -> None:
    """Single-file layout root must be a JSON object — list / scalar reject."""
    target = tmp_path / "resources" / "lang" / "en.json"
    _write_json(target, ["not", "a", "dict"])

    loader = JsonFileLoader(base_path=tmp_path)

    with pytest.raises(TranslationFileMalformedError):
        loader.load("en", "messages")


def test_supports_nested_dict_values(tmp_path: Path) -> None:
    """Translation values can be nested dicts ``Translator`` traverses by dot."""
    target = tmp_path / "resources" / "lang" / "en.json"
    _write_json(
        target,
        {"messages": {"greeting": {"morning": "Good morning", "evening": "Good evening"}}},
    )

    loader = JsonFileLoader(base_path=tmp_path)
    data = loader.load("en", "messages")

    assert data == {"greeting": {"morning": "Good morning", "evening": "Good evening"}}


def test_rejects_non_string_keys_after_decode(tmp_path: Path) -> None:
    """JSON objects always decode to ``str``-keyed dicts, so we just check
    the coerce path catches non-string-non-dict leaf values."""
    target = tmp_path / "resources" / "lang" / "en" / "messages.json"
    _write_json(target, {"hi": 42})

    loader = JsonFileLoader(base_path=tmp_path)

    with pytest.raises(TranslationFileMalformedError):
        loader.load("en", "messages")
