"""Animated stderr spinner for the slow CLI boot phase.

Provider boot drags in SQLAlchemy/FastAPI/Starlette/Jinja2 and runs
connectivity probes — a few seconds of dead air after the banner where the CLI
looks hung. This ticks a spinner so the user knows it's working. Same gating as
the banner: stderr TTY only, opt out via ``ARVEL_NO_BANNER`` / ``--no-banner``,
``NO_COLOR`` drops the ANSI styling.

Boot blocks the event loop with synchronous imports, so an asyncio task wouldn't
get a chance to tick. A daemon thread animates independently of the busy loop.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import sys
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_ANSI_DIM = "\033[2m"
_ANSI_RESET = "\033[0m"
_CLEAR_LINE = "\r\033[K"
_INTERVAL_SECONDS = 0.1


def _suppressed() -> bool:
    return bool(os.environ.get("ARVEL_NO_BANNER")) or not sys.stderr.isatty()


@contextlib.contextmanager
def boot_spinner(message: str) -> Generator[None]:
    """Animate a spinner on stderr until the block exits (success or error)."""
    if _suppressed():
        yield
        return

    stop = threading.Event()
    color = not os.environ.get("NO_COLOR")

    def _spin() -> None:
        start = time.monotonic()
        for frame in itertools.cycle(_FRAMES):
            if stop.is_set():
                break
            line = f"{frame} {message} {time.monotonic() - start:.1f}s"
            sys.stderr.write(f"\r{_ANSI_DIM}{line}{_ANSI_RESET}" if color else f"\r{line}")
            sys.stderr.flush()
            stop.wait(_INTERVAL_SECONDS)

    thread = threading.Thread(target=_spin, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)
        # Wipe the spinner line so command output / tracebacks start clean.
        sys.stderr.write(_CLEAR_LINE)
        sys.stderr.flush()


__all__ = ["boot_spinner"]
