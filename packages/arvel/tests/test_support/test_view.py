"""Tests for the Jinja2-backed view renderer (``arvel.support.view``)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from arvel.config._lookup_registry import register, reset
from arvel.support import view as view_module


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    """Create a temp directory with HTML and text Jinja templates."""
    (tmp_path / "hello.txt.j2").write_text("Hello {{ name }}!\n")
    (tmp_path / "hello.html.j2").write_text("<p>Hello {{ name }}!</p>\n")
    (tmp_path / "no_extension").write_text("Bare {{ value }}\n")
    nested = tmp_path / "mail"
    nested.mkdir()
    (nested / "verify.html.j2").write_text("<a href='{{ url }}'>verify</a>\n")
    return tmp_path


@pytest.fixture
def view_config(template_dir: Path) -> Iterator[None]:
    """Register a fake ``config/view.py`` module pointing at the temp directory.

    Reset both the config registry and the view's Environment cache so the
    next ``render_template`` call rebuilds against the new search path.
    """
    fake = ModuleType("view")
    fake.paths = [str(template_dir)]  # type: ignore[attr-defined]
    reset()
    register("view", fake)
    view_module.reset_cache()
    try:
        yield
    finally:
        reset()
        view_module.reset_cache()


class TestRenderTemplate:
    def test_renders_text_template(self, view_config: None) -> None:
        out = view_module.render_template("hello.txt.j2", {"name": "Ada"})
        assert out == "Hello Ada!\n"

    def test_text_template_does_not_autoescape(self, view_config: None) -> None:
        # Plain text templates must keep angle brackets verbatim — autoescape
        # would mangle the output for non-HTML clients.
        out = view_module.render_template("hello.txt.j2", {"name": "<test>"})
        assert out == "Hello <test>!\n"

    def test_html_template_autoescapes_user_input(self, view_config: None) -> None:
        out = view_module.render_template("hello.html.j2", {"name": "<script>"})
        assert out == "<p>Hello &lt;script&gt;!</p>\n"

    def test_renders_nested_template(self, view_config: None) -> None:
        out = view_module.render_template(
            "mail/verify.html.j2",
            {"url": "https://example.com/verify"},
        )
        assert "https://example.com/verify" in out

    def test_missing_template_raises_template_not_found(self, view_config: None) -> None:
        from jinja2 import TemplateNotFound

        with pytest.raises(TemplateNotFound):
            view_module.render_template("nonexistent.html.j2", {})


class TestResolvePathsConfig:
    def test_invalid_paths_type_raises_typeerror(self) -> None:
        fake = ModuleType("view")
        fake.paths = "not-a-list"  # type: ignore[attr-defined]
        reset()
        register("view", fake)
        view_module.reset_cache()
        try:
            with pytest.raises(TypeError, match="must be a list"):
                view_module.render_template("anything", {})
        finally:
            reset()
            view_module.reset_cache()

    def test_invalid_path_entry_raises_typeerror(self) -> None:
        fake = ModuleType("view")
        fake.paths = [123]  # type: ignore[attr-defined]
        reset()
        register("view", fake)
        view_module.reset_cache()
        try:
            with pytest.raises(TypeError, match="str or Path"):
                view_module.render_template("anything", {})
        finally:
            reset()
            view_module.reset_cache()
