"""A tiny stdlib spinner for the CLI — raw ANSI in a daemon thread, no ``rich``.

``rich`` is forbidden in the light core (G2 covers ``arvel.console``), so the loading spinner is
hand-rolled like ``console.banner`` / ``kernel.boot_report``. Gated on a TTY and ``NO_COLOR`` so it's a
no-op for piped/redirected output (no escape codes in logs). A class-based context manager (matching
``container._ScopeGuard``). Grounded in knowledge/port/13-console.md.
"""

from __future__ import annotations

import itertools
import os
import sys
import threading
import time
from typing import TextIO

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Spinner:
    """Animate a spinner with ``label`` for the duration of a ``with`` block.

    A no-op when the stream isn't a TTY or ``NO_COLOR`` is set. The animation runs in a daemon thread,
    so it keeps spinning while the body blocks on sync work *or* awaits.
    """

    __slots__ = ("_label", "_out", "_stop", "_thread")

    def __init__(self, label: str = "loading", *, stream: TextIO | None = None) -> None:
        self._label = label
        self._out: TextIO = stream if stream is not None else sys.stderr
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Spinner:
        if self._out.isatty() and not os.environ.get("NO_COLOR"):
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def _spin(self) -> None:
        for frame in itertools.cycle(_FRAMES):
            if self._stop.is_set():
                break
            self._out.write(f"\r\033[35m{frame}\033[0m {self._label}")
            self._out.flush()
            time.sleep(0.08)

    def __exit__(self, *exc: object) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=0.3)
            self._out.write("\r\033[2K")  # clear the spinner line
            self._out.flush()
