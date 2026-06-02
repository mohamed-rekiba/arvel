"""Pre-flight database checks for CLI commands.

``migrate`` needs the database reachable; ``db:seed`` needs it reachable *and*
migrated. These helpers turn a dead connection or an un-migrated schema into a
clear, actionable error instead of a raw driver traceback.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = [
    "DatabaseNotMigratedError",
    "DatabaseUnavailableError",
    "check_database_connection",
]

_DEFAULT_TIMEOUT_SECONDS = 5.0


class DatabaseUnavailableError(RuntimeError):
    """The database can't be reached — down, wrong host/port, bad auth, or timeout."""


class DatabaseNotMigratedError(RuntimeError):
    """The schema isn't ready — migrations table missing or migrations pending."""


async def check_database_connection(engine: AsyncEngine) -> None:
    """Run ``SELECT 1`` against *engine*; raise ``DatabaseUnavailableError`` on failure.

    Caps the wait at ``_DEFAULT_TIMEOUT_SECONDS`` so an unreachable host fails fast
    instead of hanging on a TCP connect.
    """
    try:
        async with asyncio.timeout(_DEFAULT_TIMEOUT_SECONDS):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except TimeoutError as exc:
        raise DatabaseUnavailableError(
            f"database did not respond within {_DEFAULT_TIMEOUT_SECONDS:.0f}s — "
            "is it running and reachable?"
        ) from exc
    except (SQLAlchemyError, OSError) as exc:
        raise DatabaseUnavailableError(f"cannot connect to the database: {exc}") from exc
