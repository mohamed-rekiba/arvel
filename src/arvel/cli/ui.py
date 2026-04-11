"""Shared UX utilities for CLI plugins.

Rich is lazily imported — ``import arvel.cli.ui`` adds zero heavyweight
dependencies to the process.
"""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING, Any, NoReturn

import typer

if TYPE_CHECKING:
    from rich.console import Console

BANNER = r"""
    _                   _
   / \   _ ____   _____| |
  / _ \ | '__\ \ / / _ \ |
 / ___ \| |   \ V /  __/ |
/_/   \_\_|    \_/ \___|_|
"""


class CliConsole:
    """Lazily-initialised Rich console with spinner, error, and success helpers."""

    def __init__(self) -> None:
        self._console: Console | None = None

    @property
    def console(self) -> Console:
        if self._console is None:
            from rich.console import Console

            self._console = Console()
        return self._console

    def spinner(self, message: str) -> Any:
        """Return a Rich ``Status`` context manager showing *message*."""
        return self.console.status(
            f"[bold cyan]{message}[/bold cyan]",
            spinner="dots",
        )

    def error(self, message: str) -> NoReturn:
        """Print a red error message to stderr and exit with code 1."""
        from rich.console import Console as RichConsole

        RichConsole(stderr=True).print(f"[red]Error:[/red] {message}")
        raise typer.Exit(code=1)

    def success(self, message: str) -> None:
        self.console.print(f"  [green]✓[/green] {message}")

    def info(self, message: str) -> None:
        self.console.print(f"  {message}")

    def banner(self) -> None:
        self.console.print(f"[bold cyan]{BANNER}[/bold cyan]")

    def print(self, message: str = "") -> None:
        self.console.print(message)


class InquirerPreloader:
    """Background-loads InquirerPy while showing a spinner instantly.

    Usage::

        preloader = InquirerPreloader()
        # ... do other work ...
        inquirer = preloader.get()  # blocks until import finishes
    """

    def __init__(self) -> None:
        self._module: Any = None
        self._done = threading.Event()
        self._stop_spinner = threading.Event()
        self._spinner_exited = threading.Event()

        threading.Thread(target=self._load, daemon=True).start()
        threading.Thread(target=self._spin, daemon=True).start()

    def _load(self) -> None:
        from InquirerPy import inquirer

        self._module = inquirer
        self._done.set()
        self._stop_spinner.set()

    def _spin(self) -> None:
        import itertools
        import time

        frames = itertools.cycle(
            ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        )
        shown = False
        while not self._stop_spinner.is_set():
            sys.stdout.write(f"\r  {next(frames)} Loading...")
            sys.stdout.flush()
            shown = True
            time.sleep(0.08)

        if shown:
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
        self._spinner_exited.set()

    def stop(self) -> None:
        """Stop the spinner and wait until the line is cleared."""
        self._stop_spinner.set()
        self._spinner_exited.wait(timeout=1.0)

    def get(self) -> Any:
        """Block until InquirerPy is loaded and return the ``inquirer`` module."""
        self._done.wait()
        return self._module
