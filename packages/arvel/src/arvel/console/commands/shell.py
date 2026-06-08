"""``shell`` — interactive Python REPL with the Arvel app pre-loaded.

Mirrors Laravel's ``artisan tinker``. Boots the framework Application, opens a
database session and binds it as the active session (so ActiveRecord helpers
like ``await User.find(1)`` work without per-call session plumbing),
auto-imports user models from ``app/models/*.py``, exposes the public facades,
and hands control to IPython — falling back to the stdlib ``code.interact``
when IPython is not installed.

The REPL owns the process (``owns_process = True``): the entrypoint dispatches
it outside its ``asyncio.run`` wrapper, and the command boots the framework
itself on the same event loop IPython uses for ``%autoawait`` — see
:meth:`ShellCommand.run_repl`.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import sys
from collections.abc import Callable
from contextvars import Token
from pathlib import Path
from types import ModuleType
from typing import Annotated, Any, ClassVar, cast

import typer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arvel.application.errors import EnvironmentNotSetError
from arvel.console import Command, Context
from arvel.console._t import Option as _Option
from arvel.console.bootstrap import bootstrap_framework_application, find_project_root
from arvel.container.errors import BindingResolutionError
from arvel.database.session import reset_active_session, set_active_session

_log = logging.getLogger("arvel.console.shell")

# Public facades to expose in the REPL namespace. Each entry is
# (binding_name, module_path, symbol_in_module). Modules that aren't importable
# (e.g. an optional extra such as ``mail`` is not installed) are skipped
# silently — the REPL still works, just without that facade.
_FACADES: tuple[tuple[str, str, str], ...] = (
    ("Cache", "arvel.facades.cache", "Cache"),
    ("Auth", "arvel.facades.auth", "Auth"),
    ("Bus", "arvel.facades.bus", "Bus"),
    ("Config", "arvel.facades", "Config"),
    ("Session", "arvel.facades.session", "Session"),
    ("Storage", "arvel.facades.storage", "Storage"),
    ("Mail", "arvel.facades.mail", "Mail"),
    ("Notification", "arvel.facades.notification", "Notification"),
    ("Broadcast", "arvel.facades.broadcast", "Broadcast"),
    ("Event", "arvel.facades.event", "Event"),
    ("Hash", "arvel.facades.hash", "Hash"),
    ("DB", "arvel.database", "DB"),
)


class ShellCommand(Command):
    name: ClassVar[str] = "shell"
    help: ClassVar[str] = "Launch an interactive REPL with the Arvel app bootstrapped"
    # The REPL drives an event loop itself: IPython's autoawait runs `await`
    # expressions on its own persistent loop, and prompt_toolkit calls
    # asyncio.run() for the prompt UI. Both would hit "asyncio.run() cannot be
    # called from a running event loop" if we ran inside the entrypoint's
    # asyncio.run wrapper. So shell owns the process and boots the framework
    # itself, on the *same* loop IPython uses for autoawait — otherwise the
    # async engine pinged during boot would be bound to a different loop than
    # the one the user's `await Model.find()` runs on.
    owns_process: ClassVar[bool] = True

    def __init__(self) -> None:
        super().__init__()
        self._active_session: AsyncSession | None = None
        self._active_session_token: Token[AsyncSession | None] | None = None

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            dry_run: Annotated[
                bool,
                _Option("--dry-run", help="Validate shell bootstrap without launching REPL"),
            ] = False,
        ) -> None:
            # --dry-run must NOT bootstrap the app — it's a cheap "does the
            # command wire up" check that must stay safe to run anywhere.
            if dry_run:
                typer.echo("Shell ready (dry run).")
                return
            cmd_self.run_repl()

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def run_repl(self) -> None:
        """Bootstrap (if in a project), build the namespace, and launch the REPL.

        Outside a project — or when bootstrap returns ``None`` — we serve a
        plain REPL with no app/DB. Inside a project we boot the framework and
        serve the REPL on IPython's autoawait loop so the engine, session, and
        user-typed ``await`` expressions all share one event loop.
        """
        project_root = find_project_root()
        framework_app = (
            bootstrap_framework_application(project_root) if project_root is not None else None
        )

        if framework_app is None:
            self.app = None
            self._serve_repl()
            return

        loop, created = self._repl_loop()
        asyncio.set_event_loop(loop)
        try:
            # Lazy boot: skip the DB connectivity probe so the REPL opens even
            # when the database is down. Queries connect on first use, Tinker-style.
            loop.run_until_complete(framework_app.boot(probe_connections=False))
            self.app = framework_app
            self._serve_repl(loop)
        finally:
            loop.run_until_complete(framework_app.shutdown())
            asyncio.set_event_loop(None)
            if created:
                loop.close()

    def _serve_repl(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        namespace = self.build_namespace()
        try:
            self.print_banner(namespace)
            self._launch_repl(namespace)
        finally:
            self.release_active_session(loop)

    @staticmethod
    def _repl_loop() -> tuple[asyncio.AbstractEventLoop, bool]:
        """Return ``(loop, created)`` for the REPL.

        Prefer IPython's persistent autoawait loop so everything the REPL
        touches (engine, session, user ``await``) lives on one loop. When
        IPython isn't installed the stdlib fallback has no autoawait, so loop
        affinity is moot and a fresh loop (which we own and close) is fine.
        """
        try:
            from IPython.core.async_helpers import get_asyncio_loop  # noqa: PLC0415
        except ImportError:
            return asyncio.new_event_loop(), True
        typed_get_loop = cast("Callable[[], asyncio.AbstractEventLoop]", get_asyncio_loop)
        return typed_get_loop(), False

    # ------------------------------------------------------------------ public

    def build_namespace(self) -> dict[str, Any]:
        """Build the REPL namespace.

        Always includes ``sys`` for diagnostics. When ``self.app`` is bound:

        - Adds ``app`` and ``container``.
        - Resolves ``async_sessionmaker`` from the container, opens an
          :class:`AsyncSession`, pushes it onto the active-session ContextVar
          (so ``Model.query()`` works without per-call session plumbing) and
          exposes it as ``session``.
        - Auto-imports user models from ``app/models/*.py`` so callers can
          type ``await User.find(1)`` without importing first.
        - Exposes every available public facade (``Cache``, ``Auth``, ``Bus``,
          ``Config``, ``Session``, ``Storage``, ``Mail``, ``Notification``,
          ``Broadcast``, ``Event``, ``Hash``, ``DB``).

        :class:`BindingResolutionError` on the session lookup is swallowed:
        CLI-only apps with no ``DatabaseServiceProvider`` registered still get
        a working REPL, just without ORM session scope.
        """
        namespace: dict[str, Any] = {"sys": sys}

        if self.app is None:
            return namespace

        namespace["app"] = self.app
        namespace["container"] = self.app.container

        self._bind_session(namespace)
        self._load_facades(namespace)
        self._autoload_models(namespace)

        return namespace

    def release_active_session(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Reset the active-session ContextVar and close the REPL session.

        Idempotent — safe to call from a ``finally`` block, and a no-op once
        the session has already been released.

        When ``loop`` is given (the REPL's loop), close on it so the session is
        torn down on the same loop it was created on. Otherwise drive
        ``close()`` from a one-shot ``asyncio.run`` loop; ``RuntimeError`` is
        swallowed and the coroutine explicitly closed so it doesn't leak as a
        "coroutine was never awaited" warning. The connection still returns to
        the pool when the engine is disposed.
        """
        if self._active_session_token is not None:
            reset_active_session(self._active_session_token)
            self._active_session_token = None

        session = self._active_session
        if session is None:
            return
        self._active_session = None

        coro = session.close()
        if loop is not None and not loop.is_closed() and not loop.is_running():
            loop.run_until_complete(coro)
            return
        try:
            asyncio.run(coro)
        except RuntimeError:
            coro.close()

    # ----------------------------------------------------------------- helpers

    def _bind_session(self, namespace: dict[str, Any]) -> None:
        if self.app is None:
            return
        try:
            maker: async_sessionmaker[AsyncSession] = self.app.container.make(
                async_sessionmaker[AsyncSession]
            )
        except BindingResolutionError:
            return

        session = maker()
        self._active_session = session
        self._active_session_token = set_active_session(session)
        namespace["session"] = session

    def _load_facades(self, namespace: dict[str, Any]) -> None:
        for facade_name, module_path, symbol in _FACADES:
            try:
                module = importlib.import_module(module_path)
            except ImportError:
                continue
            facade = getattr(module, symbol, None)
            if facade is not None:
                namespace[facade_name] = facade

    def _autoload_models(self, namespace: dict[str, Any]) -> None:
        if self.app is None:
            return
        try:
            base_path = self.app.base_path()
        except EnvironmentNotSetError:
            return

        models_dir = base_path / "app" / "models"
        if not models_dir.is_dir():
            return

        # Local import: pulls the full SQLAlchemy ORM stack, which is heavy
        # enough to avoid on REPL startup when no models directory exists.
        from arvel.database import Model  # noqa: PLC0415

        aliased: list[str] = []
        for file_path in sorted(models_dir.glob("*.py")):
            if file_path.name == "__init__.py":
                continue
            module = self._import_user_model(file_path)
            if module is None:
                continue
            aliased.extend(_collect_models(module, namespace, Model))

        if aliased:
            namespace["__arvel_aliased_models__"] = tuple(aliased)

    @staticmethod
    def _import_user_model(file_path: Path) -> ModuleType | None:
        # Reuse a module already loaded from this file (e.g. app.models.user
        # imported during boot via routes/controllers). Re-executing the file
        # under a synthetic name would re-run the `class User(Model)` definition
        # and register its table on the shared MetaData a second time, which
        # SQLAlchemy rejects ("Table 'users' is already defined") — the model
        # would then be silently skipped and missing from the REPL namespace.
        already_loaded = _find_loaded_module(file_path)
        if already_loaded is not None:
            return already_loaded

        module_name = f"arvel_user_models_{file_path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 — broken model file shouldn't crash REPL
            _log.warning("shell: skipping %s (%s)", file_path, exc)
            return None
        return module

    def print_banner(self, namespace: dict[str, Any]) -> None:
        """Print the welcome banner. Public so tests can drive it standalone."""
        typer.secho()
        typer.secho("Arvel shell — Ctrl-D to exit.", fg=typer.colors.YELLOW)
        if "session" in namespace:
            typer.secho(
                "DB session active. Wrap writes in `async with DB.transaction():` "
                "or call `await session.commit()` to persist.",
                fg=typer.colors.GREEN,
            )
        aliased = namespace.get("__arvel_aliased_models__")
        if aliased:
            typer.secho(f"Aliased models: {', '.join(aliased)}.", fg=typer.colors.CYAN)
        typer.secho()

    def _launch_repl(self, namespace: dict[str, Any]) -> None:
        try:
            _ipython: Any = importlib.import_module("IPython")
            _traitlets_config: Any = importlib.import_module("traitlets.config")
            config = _traitlets_config.Config()
            config.TerminalInteractiveShell.loop_runner = "asyncio"
            config.TerminalInteractiveShell.autoawait = True
            config.InteractiveShell.autoawait = True
            _ipython.embed(user_ns=namespace, config=config, using="asyncio", colors="neutral")
        except ImportError:
            import code  # noqa: PLC0415

            code.interact(local=namespace)


def _find_loaded_module(file_path: Path) -> ModuleType | None:
    """Return an already-imported module sourced from ``file_path``, if any.

    Matches by resolved ``__file__`` so a model imported during boot under its
    canonical dotted name (``app.models.user``) is reused instead of re-executed.
    """
    try:
        target = file_path.resolve()
    except OSError:
        return None
    for module in list(sys.modules.values()):
        mod_file = getattr(module, "__file__", None)
        if mod_file is None:
            continue
        try:
            if Path(mod_file).resolve() == target:
                return module
        except OSError, ValueError:
            continue
    return None


def _collect_models(module: ModuleType, namespace: dict[str, Any], model_base: type) -> list[str]:
    """Add every subclass of ``model_base`` exported by ``module`` to ``namespace``.

    Returns the list of names that were aliased. Existing keys in the namespace
    win on collision — mirrors Tinker's class-alias behaviour and avoids
    surprising re-bindings.
    """
    added: list[str] = []
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        attr = getattr(module, attr_name)
        if not isinstance(attr, type):
            continue
        if attr is model_base or not issubclass(attr, model_base):
            continue
        if attr_name in namespace:
            continue
        namespace[attr_name] = attr
        added.append(attr_name)
    return added


__all__ = ["ShellCommand"]
