"""``shell`` — an interactive REPL preloaded with arvel's surface, the app, and your models.

On IPython (the ``[console]`` extra) you get **top-level await** (autoawait) and autocomplete; without
it, it falls back to the stdlib REPL (no await). Inside a project it runs the sync bootstrap so the
container bindings exist and imports the app's models so they're **autoloaded by short name** (like
Tinker). Async work (``await User.find(1)``) runs on IPython's loop; arvel's pools bind lazily
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
        namespace.update(defined_models())  # autoload models by short name
    return namespace


def defined_models() -> dict[str, type]:
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


def import_app_models(app: Any) -> list[tuple[str, str]]:
    """Import the app's models (``app/models/*.py``) so they self-register into the model registry and
    can be autoloaded. Best-effort: a broken model file is skipped, not fatal to the REPL — the
    ``(filename, error)`` of each skipped file is returned so the shell can note it at startup."""
    import importlib.util
    import sys
    from pathlib import Path

    skipped: list[tuple[str, str]] = []
    models_dir = Path(app.base_path) / "app" / "models"
    if not models_dir.is_dir():
        return skipped
    for index, file in enumerate(sorted(models_dir.glob("*.py"))):
        if file.name.startswith("_"):
            continue
        try:
            modname = f"_arvel_app_model_{index}"
            spec = importlib.util.spec_from_file_location(modname, file)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                # __subclasses__ is a weakref list; a GC'd module would drop its model classes from it
                sys.modules[modname] = module
                spec.loader.exec_module(module)
        except Exception as exc:  # a broken model file is skipped, not fatal to the REPL
            skipped.append((file.name, f"{type(exc).__name__}: {exc}"))
    return skipped


def startup_banner(
    namespace: dict[str, Any],
    *,
    models: list[str],
    skipped: list[tuple[str, str]],
    header: str,
) -> str:
    """The tinker startup summary — kept short on purpose. The whole arvel surface (facades +
    helpers) and every model are in scope; ``dir()`` lists them. We advertise it in two lines
    rather than dumping ~90 names, and — so it isn't silent — flag any model files that were
    skipped on the way in."""
    lines = [header, ""]
    if "app" in namespace:
        sample = ", ".join(models[:6]) + (", …" if len(models) > 6 else "")
        detail = f" ({sample})" if models else " (none found in app/models)"
        lines.append(f"  app + {len(models)} model(s) autoloaded by short name{detail}")
    # a stable, tiny sample so it's clear the surface is loaded; dir() has the rest
    picks = [n for n in ("dd", "dump", "collect", "config", "now", "DB", "Auth") if n in namespace]
    lines.append(f"  arvel surface ready: {', '.join(picks)}, … — dir() lists everything")
    if skipped:
        lines.append("")
        lines.append(f"  ⚠ skipped {len(skipped)} model file(s) that failed to import:")
        lines.extend(f"      {name} — {err}" for name, err in skipped)
    return "\n".join(lines) + "\n"


def _launch_repl(namespace: dict[str, Any], banner: str) -> None:
    """Drop into IPython (top-level await + autocomplete) when available, else the stdlib REPL."""
    import importlib
    import os

    # prompt_toolkit sends a Cursor-Position-Request (ESC[6n) at startup and blocks waiting for the
    # terminal to answer. VS Code's integrated terminal (also tmux/mosh/some SSH) replies slowly, so
    # the REPL stalls for seconds before the first prompt. A line REPL never needs CPR — opt out so
    # startup stays sub-second there. ``setdefault`` lets a user who set it explicitly win.
    os.environ.setdefault("PROMPT_TOOLKIT_NO_CPR", "1")

    try:
        ipython = importlib.import_module("IPython")
        traitlets_config = importlib.import_module("traitlets.config")
    except ImportError:
        import code

        code.interact(
            banner=banner + "(install arvel[console] for IPython: top-level await + autocomplete)",
            local=namespace,
        )
        return

    # IPython/traitlets ship no type stubs; reached via importlib so the dynamic attrs are Any
    config: Any = traitlets_config.Config()
    config.TerminalInteractiveShell.autoawait = True  # top-level await (default on in IPython 9.x)
    config.TerminalInteractiveShell.banner1 = banner
    ipython.start_ipython(argv=[], user_ns=namespace, config=config)


shell_app = typer.Typer()


@shell_app.command()
def shell() -> None:
    """Launch an interactive REPL with the arvel surface, the app, and your models loaded."""
    from arvel.console.context import in_project

    app = None
    skipped: list[tuple[str, str]] = []
    if in_project():
        from arvel.console.kernel import load_project_app
        from arvel.kernel.bootstrap import bootstrap_app

        app = load_project_app()
        if app is not None:
            bootstrap_app(app)  # sync: register providers (bindings) + set the app + import routes
            skipped = import_app_models(app)  # register the app's models so they autoload by name
    namespace = build_namespace(app)
    models = sorted(defined_models()) if app is not None else []
    header = (
        "arvel shell — IPython · top-level await enabled"
        if app is not None
        else "arvel shell (no project detected — framework surface only)"
    )
    banner = startup_banner(namespace, models=models, skipped=skipped, header=header)
    _launch_repl(namespace, banner)
