"""CLI exception hierarchy.

All CLI errors are surfaced as human-friendly messages with no traceback.
"""

from __future__ import annotations

from arvel.foundation.exceptions import ArvelError


class ArvelCLIError(ArvelError):
    """Raised for any CLI-specific error (missing dependency, bad input, discovery failure)."""
