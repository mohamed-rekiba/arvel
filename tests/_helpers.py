"""Shared test helper functions."""

from __future__ import annotations

import re


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text.

    Rich/Typer emits escape codes even in test runners, breaking plain
    string assertions like ``"--queue" in result.output``.
    """
    return re.sub(r"\x1b\[[0-9;]*m", "", text)
