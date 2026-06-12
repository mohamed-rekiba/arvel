"""StderrChannel — logs to ``sys.stderr`` via stdlib StreamHandler."""

from __future__ import annotations

import logging
import sys

from arvel.logging.channels.base import StdlibChannel


class StderrChannel(StdlibChannel):
    """Mirrors Laravel's ``stderr`` channel driver.

    Writes to ``sys.stderr``.  Bound at construction time so test
    monkeypatching ``sys.stderr`` does not redirect these records.
    """

    def __init__(
        self,
        level: str = "info",
        bound: dict[str, object] | None = None,
    ) -> None:
        handler = logging.StreamHandler(sys.stderr)
        super().__init__(handler, name="stderr", level=level, bound=bound)


__all__ = ["StderrChannel"]
