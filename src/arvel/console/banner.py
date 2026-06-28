"""The arvel CLI banner — ARVEL wordmark with a violet→cyan gradient (raw ANSI).

Pure stdlib (no rich on the hot path). Suppressed by ``--no-banner``, ``NO_COLOR``/
``ARVEL_NO_BANNER``, non-TTY (pipes/CI), or width < 60. Grounded in doc 13.
"""

from __future__ import annotations

import os
import sys

VIOLET = (167, 139, 250)  # #A78BFA
CYAN = (34, 211, 238)  # #22D3EE

_ART = [
    " █████╗ ██████╗ ██╗   ██╗███████╗██╗",
    "██╔══██╗██╔══██╗██║   ██║██╔════╝██║",
    "███████║██████╔╝██║   ██║█████╗  ██║",
    "██╔══██║██╔══██╗╚██╗ ██╔╝██╔══╝  ██║",
    "██║  ██║██║  ██║ ╚████╔╝ ███████╗███████╗",
    "╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚══════╝",
]


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def _gradient(line: str, width: int) -> str:
    out: list[str] = []
    for x, ch in enumerate(line):
        r, g, b = _lerp(VIOLET, CYAN, x / max(width - 1, 1))
        out.append(f"\033[38;2;{r};{g};{b}m{ch}")
    return "".join(out) + "\033[0m"


def print_banner(version: str = "0.0.1") -> None:
    plain = bool(
        os.environ.get("NO_COLOR") or os.environ.get("ARVEL_NO_BANNER") or not sys.stdout.isatty()
    )
    cols = os.get_terminal_size().columns if sys.stdout.isatty() else 80
    if plain:
        print(f"arvel {version}")
        return
    if cols < 60:
        print(_gradient("▟█▙ arvel", 9) + f"\033[2m  v{version}\033[0m")
        return
    width = max(len(line) for line in _ART)
    for line in _ART:
        print(_gradient(line, width))
    print(f"\033[2m  async-first · type-safe · modular   ·   v{version}\033[0m")
