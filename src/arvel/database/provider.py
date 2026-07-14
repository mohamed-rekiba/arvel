"""DatabaseServiceProvider — binds the connection resolver (auto-discovered)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import msgspec

from arvel.database.connections import ConnectionResolver
from arvel.kernel import Settings
from arvel.kernel.service_provider import ServiceProvider

if TYPE_CHECKING:
    from arvel.kernel.application import Application


def _no_connections() -> dict[str, dict[str, Any]]:
    return {}


class DatabaseSettings(Settings):
    """Typed, validated view over the ``database`` config section (DR-0016).

    ``default`` is the active connection name; ``connections`` maps name → per-driver config and stays
    an open ``dict`` (driver-specific keys are passed through to the engine, never dropped).
    """

    __config_key__ = "database"
    default: str = "default"
    connections: dict[str, dict[str, Any]] = msgspec.field(default_factory=_no_connections)


class DatabaseServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_db(_app: Application) -> ConnectionResolver:
            settings = DatabaseSettings()  # auto-loads + validates config("database")
            if settings.connections:
                return ConnectionResolver(settings.connections, default=settings.default)
            return ConnectionResolver()

        self.app.singleton("db", make_db)

        def make_migrator(app: Application) -> Any:
            from arvel.database.migrations import Migrator

            return Migrator(app.make("db"))

        self.app.singleton("migrator", make_migrator)

    def boot(self) -> None:
        app = self.app

        # Register the database as a health-checked resource (DR-0039). It owns its own lifecycle —
        # connect warms + verifies the pool, disconnect disposes it — so no separate terminating hook.
        if DatabaseSettings().connections:
            from arvel.database.resource import DatabaseResource

            critical = bool(app.config("database.critical", True))
            app.resources.register(DatabaseResource(app.make("db"), critical=critical))

        # runs in boot so every provider's load_migrations_from() has already appended its paths
        if not app.bound("migrations"):
            from arvel.database.migrations import discover_migrations

            paths = [*app.registry("database.migration_paths", list), "database/migrations"]
            app.instance("migrations", discover_migrations(paths, app.base_path))
