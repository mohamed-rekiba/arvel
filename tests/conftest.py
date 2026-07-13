"""Suite-wide hygiene fixtures."""

from __future__ import annotations

import pytest

from arvel.support.context import Context


@pytest.fixture(autouse=True)
def _fresh_context() -> None:
    """Ambient context must never leak between tests — reset both channels up front.
    (Reset-before, not after: it also shields against residue from a crashed test.)"""
    Context.flush()
