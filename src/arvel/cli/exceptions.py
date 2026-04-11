"""CLI exception hierarchy.

All CLI errors are surfaced as human-friendly messages with no traceback.
"""

from __future__ import annotations


class ArvelCLIError(Exception):
    """Raised for any CLI-specific error (missing dependency, bad input, discovery failure)."""


class CliValidationError(ArvelCLIError):
    """Raised by input validation to signal an error before exit.

    Command entry points catch this and display the message via
    ``CliConsole.error()``, ensuring any active spinner clears first.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
