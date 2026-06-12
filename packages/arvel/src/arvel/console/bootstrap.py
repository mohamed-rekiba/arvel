"""Lazy framework Application bootstrap for the ``arvel`` CLI.

The framework ``arvel.application.Application`` is the kernel that owns the DI
container and provider lifecycle. CLI commands that need DI (queue, scheduler,
shell, ...) opt in by declaring ``requires`` (a frozenset of ``CliSubsystem``)
on their ``Command`` subclass; the entrypoint then walks up from cwd to
discover the user's ``bootstrap/app.py``, imports it, and calls
``create_application`` — passing the resolved subsystem closure so the app
only boots the providers the command actually needs.

Discovery walks ``_MAX_ANCESTOR_DEPTH = 4`` parent directories of the start path
(cwd by default), which covers the common ``apps/<name>/<sub>/...`` layouts
without ever wandering across filesystem roots.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.application import Application
    from arvel.console._subsystem import CliSubsystem

_log = logging.getLogger("arvel.console.bootstrap")

_BOOTSTRAP_RELPATH = Path("bootstrap") / "app.py"
_MAX_ANCESTOR_DEPTH = 4


def find_project_root(start: Path | None = None) -> Path | None:
    """Return the nearest ancestor of ``start`` (or cwd) containing ``bootstrap/app.py``.

    Walks up to ``_MAX_ANCESTOR_DEPTH`` parents (5 directories total including
    ``start`` itself). Returns ``None`` when no candidate is found rather than
    raising — callers decide whether the absence is a fatal error or just
    "we're outside a project, fall back to entry-point commands only".
    """
    base = start if start is not None else Path.cwd()
    base = base.resolve()
    for candidate in [base, *base.parents[:_MAX_ANCESTOR_DEPTH]]:
        if (candidate / _BOOTSTRAP_RELPATH).is_file():
            return candidate
    return None


def bootstrap_framework_application(
    base_path: Path | None = None,
    *,
    required_subsystems: frozenset[CliSubsystem] | None = None,
) -> Application | None:
    """Import the user's ``bootstrap/app.py`` and return its ``create_application()`` result.

    ``required_subsystems`` is the transitive closure of CLI subsystems the
    invoking command needs (see ``arvel.console._subsystem.closure``). When
    supplied and the user's factory accepts a ``required_subsystems`` kwarg,
    we forward it so the application boots only the matching providers. The
    parameter is optional — older bootstrap files that don't accept it stay
    backward-compatible (full chain boots).

    Returns ``None`` when:
    - no project root is found anywhere along the ancestor chain, or
    - ``bootstrap/app.py`` exists but does not export a ``create_application``
      symbol (logged as a warning so the user knows their file is incomplete).

    Propagates ``ImportError``/``ModuleNotFoundError`` from the user's module
    verbatim — those indicate real bugs the user wants to see, not "no project".
    """
    root = find_project_root(base_path)
    if root is None:
        return None

    module_path = root / _BOOTSTRAP_RELPATH
    spec = importlib.util.spec_from_file_location("arvel_user_bootstrap_app", module_path)
    if spec is None or spec.loader is None:
        _log.warning("Could not load module spec for %s.", module_path)
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise

    factory = getattr(module, "create_application", None)
    if factory is None:
        _log.warning(
            "%s does not export create_application(); skipping framework bootstrap.",
            module_path,
        )
        return None
    if not callable(factory):
        msg = f"{module_path}: create_application must be callable, got {type(factory).__name__!r}."
        raise TypeError(msg)

    return _call_factory(factory, required_subsystems)


def _call_factory(
    factory: Callable[..., object],
    required_subsystems: frozenset[CliSubsystem] | None,
) -> Application:
    result = _invoke_factory(factory, required_subsystems)

    from arvel.application import Application  # noqa: PLC0415 — avoid import cycle at load

    if not isinstance(result, Application):
        msg = (
            "create_application() must return an arvel.application.Application, "
            f"got {type(result).__name__!r}."
        )
        raise TypeError(msg)
    return result


def _invoke_factory(
    factory: Callable[..., object],
    required_subsystems: frozenset[CliSubsystem] | None,
) -> object:
    if required_subsystems is None:
        return factory()

    try:
        sig = inspect.signature(factory)
    except TypeError, ValueError:
        # Can't introspect (e.g. a C-callable) — boot the full chain, but say so:
        # the requested subsystem filtering is silently lost otherwise.
        _log.warning(
            "Could not introspect create_application(); booting the full provider "
            "chain instead of just %s.",
            sorted(s.name for s in required_subsystems),
        )
        return factory()

    if "required_subsystems" in sig.parameters:
        return factory(required_subsystems=required_subsystems)
    return factory()


__all__ = ["bootstrap_framework_application", "find_project_root"]
