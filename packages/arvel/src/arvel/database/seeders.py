"""Seeders — populate the database with reference / fixture data."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Seeder(ABC):
    """Base class for seeders.

    Override :meth:`run` to insert rows. Seeders MUST NOT call
    ``session.commit()``; the caller (CLI / pytest fixture) owns the
    transaction.
    """

    @abstractmethod
    async def run(self) -> None: ...

    def call(self, seeder: Seeder) -> Seeder:
        """Schedule another seeder to run after this one (composition helper)."""
        return seeder


class DatabaseSeeder(Seeder):
    """Default entrypoint. Apps subclass this and call ``self.call(OtherSeeder())``.

    The CLI's ``arvel db:seed`` runs this class. It blocks if
    ``APP_ENV == "production"`` to prevent fixture data leaking into prod.
    """

    async def run(self) -> None:
        from arvel.config import config

        if config("app.is_production", default=False):
            raise RuntimeError(
                "DatabaseSeeder.run blocked: app.env=production. "
                "Set the env or override this guard explicitly."
            )


__all__ = ["DatabaseSeeder", "Seeder"]
