"""The arvel CLI banner — printed on a bare ``arvel`` invocation (no command). Plain text, no color
(doc 13). On a non-TTY (pipe/CI) or with ``ARVEL_NO_BANNER`` set it collapses to a single
``arvel <version>`` line so captured/scripted output stays clean."""

from __future__ import annotations

import os
import sys

_BANNER = r"""
   __ _  _ ____   __  ___  __
  / _` || '__\ \ / / / _ \| |
 | (_| || |   \ V / |  __/| |
  \__,_||_|    \_/   \___||_|
"""


def print_banner(version: str = "0.0.1") -> None:
    if os.environ.get("ARVEL_NO_BANNER") or not sys.stdout.isatty():
        print(f"arvel {version}")
        return
    print(_BANNER.strip("\n"))
    print(f"  arvel · async-first · type-safe · modular   ·   v{version}\n")
