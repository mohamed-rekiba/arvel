"""Shared fixtures for search module tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def clean_search_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all SEARCH_ env vars so tests start from known defaults."""
    import os

    for key in list(os.environ):
        if key.startswith("SEARCH_"):
            monkeypatch.delenv(key, raising=False)
