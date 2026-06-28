"""``shell`` — an interactive REPL preloaded with arvel's surface, the app, and your models.

On IPython (the ``[console]`` extra) you get **top-level await** (autoawait) and autocomplete; without
it, it falls back to the stdlib REPL (no await). Inside a project it runs the sync bootstrap so the
container bindings exist and imports the app's models so they're **autoloaded by short name** (like
Laravel Tinker). Async work (``await User.find(1)``) runs on IPython's loop; arvel's pools bind lazily
to that loop. Grounded in knowledge/port/13-console.md.
"""

from __future__ import annotations

from typing import Any

import typer


def build_namespace(app: Any = None) -> dict[str, Any]:
    """The REPL locals: arvel's public surface, plus — when an app is loaded — the ``app`` and every
    defined model by its short name (autoload)."""
    import arvel

    namespace: dict[str, Any] = {name: getattr(arvel, name) for name in arvel.__all__}
    if app is not None:
        namespace["app"] = app
        namespace.update(_defined_models())  # autoload models by short name (Laravel-tinker style)
    return namespace


def _defined_models() -> dict[str, type]:
    """Every defined ``Model`` subclass, by short name. Walks the live subclass tree (not the morph
    ``_MODEL_REGISTRY``, which only holds table-backed models) so even a freshly-generated model
    without ``__fields__`` yet is reachable in the REPL.

    ``Model`` is reached via arvel's lazy public API (``arvel.Model``) rather than importing
    ``arvel.database`` directly — the heavy load happens at runtime on attribute access, keeping
    ``arvel.console`` import-light (G2). import-linter only sees ``import arvel``.
    """
    import arvel

    model_base: Any = arvel.Model
    found: dict[str, type] = {}
    stack = list(model_base.__subclasses__())
    while stack:
        cls = stack.pop()
        found[cls.__name__] = cls
        stack.extend(cls.__subclasses__())
    return found


def _import_app_models(app: Any) -> None:
    """Import the app's models (``app/models/*.py``) so they self-register into the model registry and
    can be autoloaded. Best-effort: a broken model file is skipped, not fatal to the REPL."""
    import contextlib
    import importlib.util
    import sys
    from pathlib import Path

    models_dir = Path(app.base_path) / "app" / "models"
    if not models_dir.is_dir():
        return
    for index, file in enumerate(sorted(models_dir.glob("*.py"))):
        if file.name.startswith("_"):
            continue
        with contextlib.suppress(Exception):
            modname = f"_arvel_app_model_{index}"
            spec = importlib.util.spec_from_file_location(modname, file)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                # Register in sys.modules so the imported model classes stay referenced — Model
                # subclasses are tracked via weakrefs (__subclasses__), so a GC'd module drops them.
                sys.modules[modname] = module
                spec.loader.exec_module(module)


def _launch_repl(namespace: dict[str, Any]) -> None:
    """Drop into IPython (top-level await + autocomplete) when available, else the stdlib REPL."""
    import importlib

    try:
        ipython = importlib.import_module("IPython")
        traitlets_config = importlib.import_module("traitlets.config")
    except ImportError:
        import code

        code.interact(
            banner="arvel shell (install arvel[console] for IPython: top-level await + autocomplete)",
            local=namespace,
        )
        return

    # IPython/traitlets ship no type stubs — reached via importlib so the dynamic attrs are Any
    # (no suppressions, no static heavy-import edge).
    config: Any = traitlets_config.Config()
    config.TerminalInteractiveShell.autoawait = True  # top-level await (default on in IPython 9.x)
    config.TerminalInteractiveShell.banner1 = "arvel shell — IPython · top-level await enabled\n"
    ipython.start_ipython(argv=[], user_ns=namespace, config=config)


shell_app = typer.Typer()


@shell_app.command()
def shell() -> None:
    """Launch an interactive REPL with the arvel surface, the app, and your models loaded."""
    from arvel.console.context import in_project

    app = None
    if in_project():
        from arvel.console.kernel import load_project_app
        from arvel.kernel.bootstrap import bootstrap_app

        app = load_project_app()
        if app is not None:
            bootstrap_app(app)  # sync: register providers (bindings) + set the app + import routes
            _import_app_models(app)  # register the app's models so they autoload by name
    _launch_repl(build_namespace(app))
