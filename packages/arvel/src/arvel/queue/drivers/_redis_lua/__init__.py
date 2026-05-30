"""Lua scripts shipped with the redis-direct queue driver (WI-018, ADR-066).

The file ``promote_and_pop.lua`` is loaded once per ``RedisConnection``
instance via ``SCRIPT LOAD`` and invoked via ``EVALSHA`` on every pop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

PROMOTE_AND_POP_LUA: Final[str] = (Path(__file__).parent / "promote_and_pop.lua").read_text(
    encoding="utf-8"
)

__all__ = ["PROMOTE_AND_POP_LUA"]
