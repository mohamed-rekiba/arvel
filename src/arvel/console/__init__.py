"""arvel.console — the CLI entry point (built on Typer + LazyGroup; DR-0002).

The root is a ``typer.Typer`` whose group class is :class:`~arvel.console.lazy.LazyGroup`,
so the dispatcher imports only the invoked command's module (T0 budget). ``main``
keeps the hottest paths (``--version``) on a stdlib fast-path that imports neither
typer nor rich. Heavy work (the full app boot for project commands) is deferred to
the command body. Grounded in knowledge/port/13-console.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import typer


class Command:
    """Base class for app/ecosystem commands (Typer-wrapped at registration)."""

    signature: str = ""
    description: str = ""

    async def handle(self, *deps: Any) -> Any:  # DI-injected by the kernel
        raise NotImplementedError

    def info(self, message: str) -> None:
        print(message)

    def line(self, message: str = "") -> None:
        print(message)


def build_cli() -> typer.Typer:
    """Construct the Typer application with the lazy command tree."""
    import typer

    from arvel.console.lazy import LazyGroup

    app = typer.Typer(cls=LazyGroup, add_completion=False, no_args_is_help=True)

    @app.callback()
    def _root() -> None:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        """arvel — a batteries-included async web framework for Python."""

    return app


def main() -> None:
    """Run the arvel CLI. ``--version`` and the bare banner are answered before
    importing Typer (T0 fast path — no typer/rich import)."""
    import sys

    argv = sys.argv[1:]
    if argv and argv[0] in ("--version", "-V"):
        from arvel import __version__

        print(__version__)
        return
    if not argv:
        from arvel import __version__
        from arvel.console.banner import print_banner

        print_banner(__version__)
        return
    build_cli()()
