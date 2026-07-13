"""Shell (REPL) namespace + lang:list locale discovery."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

import pytest

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
    assert namespace.get("WidgetThing") is WidgetThing  # autoloaded by short name


def test_import_app_models_registers_them_for_autoload(tmp_path: Path) -> None:
    from arvel.console.shell import import_app_models
    from arvel.kernel import Application

    models = tmp_path / "app" / "models"
    models.mkdir(parents=True)
    (models / "gadget.py").write_text(
        "from arvel.database import Model\n\n\nclass Gadget(Model):\n    __table_name__ = 'gadgets'\n"
    )
    app = Application(base_path=str(tmp_path))
    import_app_models(app)  # imports app/models/*.py so they self-register
    assert "Gadget" in build_namespace(app)


def test_import_app_models_reports_files_it_skipped(tmp_path: Path) -> None:
    from arvel.console.shell import import_app_models
    from arvel.kernel import Application

    models = tmp_path / "app" / "models"
    models.mkdir(parents=True)
    (models / "broken.py").write_text("this is not valid python :::")
    (models / "ok.py").write_text(
        "from arvel.database import Model\n\n\nclass OkModel(Model):\n    __table_name__ = 'ok'\n"
    )
    app = Application(base_path=str(tmp_path))
    skipped = import_app_models(app)  # broken file is skipped, not fatal
    assert [name for name, _ in skipped] == ["broken.py"]
    assert "SyntaxError" in skipped[0][1]
    assert "OkModel" in build_namespace(app)  # the good one still loaded


def test_startup_banner_is_concise_and_notes_skips() -> None:
    from arvel.console.shell import startup_banner

    namespace = {"app": object(), "User": object, "dd": lambda *a: None, "DB": object}
    banner = startup_banner(
        namespace,
        models=["User"],
        skipped=[("legacy.py", "ImportError: boom")],
        header="arvel shell",
    )
    assert "1 model(s) autoloaded" in banner and "User" in banner  # models summarised
    assert "dd" in banner and "DB" in banner and "dir()" in banner  # surface advertised, not dumped
    assert "skipped 1 model file" in banner and "legacy.py" in banner  # the skip note survives
    # concise: the surface is *sampled*, not dumped — a full listing would carry these names
    namespace.update({"windows_os": lambda: False, "resource_path": lambda p="": p})
    assert "windows_os" not in banner and "resource_path" not in banner


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


def test_import_app_models_returns_early_when_no_models_dir(tmp_path: Path) -> None:
    from arvel.console.shell import import_app_models
    from arvel.kernel import Application

    app = Application(base_path=str(tmp_path))  # no app/models directory at all
    import_app_models(app)  # must not raise; just nothing to import


def test_import_app_models_skips_underscore_files_among_several(tmp_path: Path) -> None:
    from arvel.console.shell import import_app_models
    from arvel.kernel import Application

    models = tmp_path / "app" / "models"
    models.mkdir(parents=True)
    (models / "_helpers.py").write_text("raise RuntimeError('must never be imported')")
    (models / "widget.py").write_text(
        "from arvel.database import Model\n\n\nclass ShellWidget(Model):\n"
        "    __table_name__ = 'shell_widgets'\n"
    )
    app = Application(base_path=str(tmp_path))
    import_app_models(app)  # two files: exercises both the skip and the loop-continue paths
    assert "ShellWidget" in build_namespace(app)


def test_launch_repl_uses_ipython_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from arvel.console.shell import _launch_repl

    calls: dict[str, Any] = {}

    import IPython

    def fake_start_ipython(*, argv: list[str], user_ns: dict[str, Any], config: Any) -> None:
        calls["argv"] = argv
        calls["user_ns"] = user_ns
        calls["config"] = config

    monkeypatch.setattr(IPython, "start_ipython", fake_start_ipython)

    namespace = {"x": 1}
    monkeypatch.delenv("PROMPT_TOOLKIT_NO_CPR", raising=False)
    _launch_repl(namespace, "banner\n")

    assert calls["argv"] == []
    assert calls["user_ns"] is namespace
    assert calls["config"].TerminalInteractiveShell.autoawait is True
    # opt out of prompt_toolkit's Cursor-Position-Request so startup doesn't stall for seconds on
    # VS Code / tmux / SSH terminals that answer the query slowly
    assert os.environ["PROMPT_TOOLKIT_NO_CPR"] == "1"


def test_launch_repl_respects_an_explicit_no_cpr_override(monkeypatch: pytest.MonkeyPatch) -> None:
    import IPython

    from arvel.console.shell import _launch_repl

    monkeypatch.setattr(IPython, "start_ipython", lambda **kw: None)
    monkeypatch.setenv("PROMPT_TOOLKIT_NO_CPR", "0")  # a user who set it explicitly wins
    _launch_repl({"x": 1}, "banner\n")
    assert os.environ["PROMPT_TOOLKIT_NO_CPR"] == "0"


def test_launch_repl_falls_back_to_stdlib_repl_without_ipython(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from arvel.console.shell import _launch_repl

    real_import_module = importlib.import_module

    def fake_import_module(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in ("IPython", "traitlets.config"):
            raise ImportError(name)
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    calls: dict[str, Any] = {}

    def fake_interact(*, banner: str, local: dict[str, Any]) -> None:
        calls["banner"] = banner
        calls["local"] = local

    import code

    monkeypatch.setattr(code, "interact", fake_interact)

    namespace = {"y": 2}
    _launch_repl(namespace, "arvel shell\n")

    assert "IPython" in calls["banner"]
    assert calls["local"] is namespace


def test_shell_command_outside_a_project_launches_with_no_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.console.context
    import arvel.console.shell as shell_module

    monkeypatch.setattr(arvel.console.context, "in_project", lambda: False)
    launched: dict[str, Any] = {}
    monkeypatch.setattr(
        shell_module, "_launch_repl", lambda ns, banner: launched.setdefault("ns", ns)
    )

    shell_module.shell()

    assert "Model" in launched["ns"]  # the public surface still loads, no project bootstrap ran


def test_shell_command_inside_a_project_bootstraps_and_autoloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.console.context
    import arvel.console.kernel
    import arvel.console.shell as shell_module
    import arvel.kernel.bootstrap
    from arvel.kernel import Application

    fake_app = Application()
    monkeypatch.setattr(arvel.console.context, "in_project", lambda: True)
    monkeypatch.setattr(arvel.console.kernel, "load_project_app", lambda: fake_app)
    bootstrapped: dict[str, Any] = {}
    monkeypatch.setattr(
        arvel.kernel.bootstrap, "bootstrap_app", lambda app: bootstrapped.setdefault("app", app)
    )
    monkeypatch.setattr(shell_module, "import_app_models", lambda app: [])
    launched: dict[str, Any] = {}
    monkeypatch.setattr(
        shell_module, "_launch_repl", lambda ns, banner: launched.setdefault("ns", ns)
    )

    shell_module.shell()

    assert bootstrapped["app"] is fake_app
    assert launched["ns"]["app"] is fake_app


def test_shell_command_in_project_with_no_loadable_app_skips_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.console.context
    import arvel.console.kernel
    import arvel.console.shell as shell_module

    monkeypatch.setattr(arvel.console.context, "in_project", lambda: True)
    monkeypatch.setattr(arvel.console.kernel, "load_project_app", lambda: None)
    launched: dict[str, Any] = {}
    monkeypatch.setattr(
        shell_module, "_launch_repl", lambda ns, banner: launched.setdefault("ns", ns)
    )

    shell_module.shell()  # app is None: bootstrap/import_app_models never run, no crash

    assert "Model" in launched["ns"]
