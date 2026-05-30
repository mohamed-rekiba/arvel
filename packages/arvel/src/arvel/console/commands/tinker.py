"""tinker — alias for the shell command (Laravel artisan parity)."""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands.shell import ShellCommand


class TinkerCommand(ShellCommand):
    """Identical to :class:`ShellCommand` but registered under ``tinker``."""

    name: ClassVar[str] = "tinker"
    help: ClassVar[str] = "Alias for `shell` — interactive Python REPL with Arvel bootstrapped"
