"""Tests for Translator — FR-015-022, FR-015-023, FR-015-025, NFR-015-006, SEC-015-003."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from arvel.i18n import Translator


@pytest.fixture
def lang_dir(tmp_path: Path) -> Iterator[Path]:
    """Build a tiny resources/lang/{en,fr}/messages.py tree on disk."""
    base = tmp_path / "resources" / "lang"
    (base / "en").mkdir(parents=True)
    (base / "fr").mkdir(parents=True)
    (base / "en" / "__init__.py").write_text("")
    (base / "fr" / "__init__.py").write_text("")
    (base / "__init__.py").write_text("")
    (tmp_path / "resources" / "__init__.py").write_text("")

    (base / "en" / "messages.py").write_text(
        dedent(
            '''
            """English."""
            translations = {
                "welcome": "Welcome, :name!",
                "nested": {"greeting": "Hello"},
                "literal": "Hello {name}",
            }
            '''
        )
    )
    (base / "fr" / "messages.py").write_text(
        dedent(
            '''
            """French."""
            translations = {
                "welcome": "Bienvenue, :name !",
                "nested": {"greeting": "Bonjour"},
                "literal": "Salut {name}",
            }
            '''
        )
    )

    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    sys.path.remove(str(tmp_path))
    # Clean up imports so the next test gets a fresh module
    for mod in list(sys.modules):
        if mod.startswith("resources"):
            del sys.modules[mod]


@pytest.fixture
def translator(lang_dir: Path) -> Translator:
    from arvel.i18n import Translator
    from arvel.i18n.loader import PythonFileLoader

    return Translator(loader=PythonFileLoader(base_path=lang_dir), default_locale="en")


class TestBasicTranslation:
    """FR-015-022 — Translator.get returns the translation."""

    def test_get_returns_english(self, translator: Translator) -> None:
        # Note: AC1 expects literal string when no replacement happens
        assert translator.get("messages.welcome", replace={"name": "Alice"}) == "Welcome, Alice!"

    def test_set_locale_changes_language(self, translator: Translator) -> None:
        translator.set_locale("fr")
        assert translator.get("messages.welcome", replace={"name": "Alice"}) == "Bienvenue, Alice !"

    def test_get_locale_returns_current(self, translator: Translator) -> None:
        translator.set_locale("fr")
        assert translator.get_locale() == "fr"


class TestMissingKey:
    """FR-015-022 — missing key returns the key verbatim."""

    def test_missing_key_returns_key(self, translator: Translator) -> None:
        out = translator.get("messages.nonexistent")
        assert out == "messages.nonexistent"


class TestDotNotation:
    """FR-015-025 — dot notation traverses nested dicts."""

    def test_dot_traversal(self, translator: Translator) -> None:
        assert translator.get("messages.nested.greeting") == "Hello"


class TestSubstitutionStyles:
    """FR-015-026 — Both :placeholder and {placeholder} work."""

    def test_laravel_style_colon(self, translator: Translator) -> None:
        assert translator.get("messages.welcome", replace={"name": "Bob"}) == "Welcome, Bob!"

    def test_python_style_braces(self, translator: Translator) -> None:
        assert translator.get("messages.literal", replace={"name": "Bob"}) == "Hello Bob"


class TestNamespaceCache:
    """NFR-015-006 — second lookup of same key incurs no file I/O."""

    def test_namespace_cached_after_first_lookup(self, translator: Translator) -> None:
        translator.get("messages.welcome")
        assert ("en", "messages") in translator.cached_namespaces()


class TestHelpers:
    """FR-015-023 — module-level __() helper proxies to current Translator."""

    def test_helper_uses_bound_translator(self, translator: Translator) -> None:
        from arvel.i18n.helpers import __ as t
        from arvel.i18n.helpers import bind_translator, unbind_translator

        bind_translator(translator)
        try:
            assert t("messages.welcome", name="Carol") == "Welcome, Carol!"
        finally:
            unbind_translator()


class TestNoCodeEval:
    """SEC-015-003 — translation parameters never evaluated as code."""

    def test_parameter_with_python_expr_is_rendered_literally(self, translator: Translator) -> None:
        malicious = "{__import__('os').system('echo PWNED')}"
        out = translator.get("messages.welcome", replace={"name": malicious})
        # Verify the literal text appears unchanged in the output and no eval occurred
        assert malicious in out
