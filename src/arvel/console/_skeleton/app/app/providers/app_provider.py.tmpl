"""The application's service provider — register bindings + boot-time wiring."""

from arvel.kernel import ServiceProvider


class AppServiceProvider(ServiceProvider):
    def register(self) -> None:
        """Bind your services into the container."""
        # Make `arvel db:seed` run the root seeder.
        from database.seeders.database_seeder import DatabaseSeeder

        self.app.singleton("seeder", lambda _app: DatabaseSeeder())

    def boot(self) -> None:
        """Boot-time wiring (runs after every provider has registered)."""
