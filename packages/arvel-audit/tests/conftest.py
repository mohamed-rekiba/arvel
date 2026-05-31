"""Fixtures for arvel-audit tests — APP_KEY, table creation, context reset.

Test models are defined inside each test module (unique table names) rather
than shared here, so this package's tests stay in the flat type-check run with
no bare cross-file imports.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from arvel.context.facade import Context
from arvel.database.model import Model
from arvel_audit import ActivityEntry, AuditEntry
from sqlalchemy.ext.asyncio import AsyncEngine

# Deterministic 32-byte key so the app encrypter round-trips in encryption tests.
os.environ.setdefault("APP_KEY", "base64:" + base64.b64encode(b"k" * 32).decode())

# Keep references so linters don't drop the table-registering imports.
_MODELS = (AuditEntry, ActivityEntry)


@pytest_asyncio.fixture
async def tables(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
def reset_context() -> Iterator[None]:
    yield
    Context.flush()
