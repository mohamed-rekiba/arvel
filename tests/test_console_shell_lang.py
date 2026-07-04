"""Shell (REPL) namespace + lang:list locale discovery."""

from __future__ import annotations

from pathlib import Path

from arvel.console.lang import list_locales
from arvel.console.lazy import LazyGroup
from arvel.console.shell import build_namespace


def test_shell_namespace_has_public_surface() -> None:
    namespace = build_namespace()
    assert "Model" in namespace
    assert "Collection" in namespace
    assert namespace["config"] is not None


def test_shell_namespace_loads_app_and_autoloads_models() -> None:
    # with an app loaded, the REPL namespace exposes `app` + every registered model by name
    from arvel.database import Model
    from arvel.kernel import Application

    class WidgetThing(Model):  # registers into the model registry on definition
        __table_name__ = "widget_things"

    app = Application()
    namespace = build_namespace(app)
    assert namespace["app"] is app
    assert (
        namespace.get("WidgetThing") is WidgetThing
    )  # autoloaded by short name (Laravel-tinker style)


def test_import_app_models_registers_them_for_autoload(tmp_path: Path) -> None:
    from arvel.console.shell import _import_app_models
    from arvel.kernel import Application

    models = tmp_path / "app" / "models"
    models.mkdir(parents=True)
    (models / "gadget.py").write_text(
        "from arvel.database import Model\n\n\nclass Gadget(Model):\n    __table_name__ = 'gadgets'\n"
    )
    app = Application(base_path=str(tmp_path))
    _import_app_models(app)  # imports app/models/*.py so they self-register
    assert "Gadget" in build_namespace(app)


def test_lang_list_finds_dir_and_file_locales(tmp_path: Path) -> None:
    (tmp_path / "en").mkdir()
    (tmp_path / "es.json").write_text("{}")
    (tmp_path / ".hidden").write_text("")
    (tmp_path / "notes.txt").write_text("")
    assert list_locales(tmp_path) == ["en", "es"]


def test_lang_list_empty_when_missing(tmp_path: Path) -> None:
    assert list_locales(tmp_path / "nope") == []


def test_shell_and_lang_registered() -> None:
    manifest = set(LazyGroup.commands_manifest)
    assert {"shell", "lang:list"} <= manifest
