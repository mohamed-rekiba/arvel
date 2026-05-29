"""Storage conftest — shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.storage.drivers.local import LocalDriver
from arvel.storage.drivers.memory import MemoryDriver


@pytest.fixture
def memory_driver() -> MemoryDriver:
    return MemoryDriver()


@pytest.fixture
def local_driver(tmp_path: Path) -> LocalDriver:
    return LocalDriver(root=tmp_path, base_url="http://localhost:8000")
