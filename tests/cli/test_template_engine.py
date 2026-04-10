"""Tests for the template engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.cli.templates.engine import (
    builtin_template_names,
    create_environment,
    render_template,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestTemplateEngine:
    def test_builtin_templates_exist(self) -> None:
        names = builtin_template_names()
        assert len(names) > 0
        assert "model.py.j2" in names
        assert "controller.py.j2" in names
        assert "migration.py.j2" in names

    def test_render_model_template(self) -> None:
        result = render_template(
            "model.py.j2",
            {
                "class_name": "User",
                "table_name": "users",
            },
        )
        assert "class User(ArvelModel)" in result
        assert '__tablename__ = "users"' in result

    def test_user_stubs_take_precedence(self, tmp_path: Path) -> None:
        stubs_dir = tmp_path / "stubs"
        stubs_dir.mkdir()
        (stubs_dir / "model.py.j2").write_text("CUSTOM: {{ class_name }}")

        env = create_environment(tmp_path)
        template = env.get_template("model.py.j2")
        result = template.render(class_name="Order")
        assert result == "CUSTOM: Order"

    def test_fallback_to_builtin_when_no_user_stubs(self, tmp_path: Path) -> None:
        result = render_template(
            "model.py.j2",
            {
                "class_name": "Order",
                "table_name": "orders",
            },
            project_dir=tmp_path,
        )
        assert "class Order(ArvelModel)" in result
