"""Shared fixtures for auth tests.

These tests are RED until the implementation lands in S25.1-S25.4. Model-level
fixtures (``engine`` / ``session``) come from the workspace-root ``conftest.py``
- in-memory async SQLite with the active session pre-bound.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def in_memory_app() -> Any:
    """Build an arvel Application with the auth subsystem wired against fakes."""
    pytest.skip("requires AuthBroker + AuthServiceProvider - pending S25.1/S25.3")


@pytest.fixture
def fake_user_provider() -> Any:
    """Stub user provider used by broker unit tests."""
    pytest.skip("requires UserProvider stub set - S25.1")
