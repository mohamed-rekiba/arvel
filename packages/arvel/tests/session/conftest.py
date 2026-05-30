"""Session conftest — shared fixtures."""

from __future__ import annotations

import pytest
from arvel.session import SessionData


@pytest.fixture
def empty_session() -> SessionData:
    return SessionData(data={})


@pytest.fixture
def session_with_data() -> SessionData:
    return SessionData(data={"user_id": 42, "name": "Alice"})
