"""DatabaseResource — the database as a health-checkable, lifecycle-managed resource (DR-0039).

Registered by ``DatabaseServiceProvider`` when a connection is configured. ``connect`` warms +
verifies the pool at boot (fail-fast readiness), ``check`` re-verifies at runtime (reused by
``/health``), ``disconnect`` disposes the pools at shutdown — so the database's teardown lives here
with its lifecycle, not as a separate ``terminating`` callback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.contracts import HealthResult, HealthStatus

if TYPE_CHECKING:
    from arvel.database.connections import ConnectionResolver


class DatabaseResource:
    """A ``SELECT 1`` liveness probe over the default connection. Critical: a database that can't be
    reached aborts boot (an app can't serve traffic without it)."""

    name = "database"

    def __init__(self, db: ConnectionResolver, *, critical: bool = True) -> None:
        self._db = db
        self.critical = critical

    async def connect(self) -> None:
        # open + verify the pool eagerly so a dead DB fails the startup gate instead of the first request
        await self._db.select("SELECT 1")

    async def disconnect(self) -> None:
        await self._db.dispose()

    async def check(self) -> HealthResult:
        await self._db.select("SELECT 1")
        return HealthResult(HealthStatus.OK, detail="SELECT 1")
