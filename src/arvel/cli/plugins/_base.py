"""Plugin protocol for CLI command registration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import typer


@runtime_checkable
class CliPlugin(Protocol):
    """Contract every CLI command plugin must satisfy.

    Plugins are structural subtypes — any object with matching ``name``,
    ``help``, and ``register`` satisfies this protocol without inheritance.
    """

    name: str
    help: str

    def register(self, app: typer.Typer) -> None:
        """Register commands or sub-apps on the parent Typer application."""
        ...
