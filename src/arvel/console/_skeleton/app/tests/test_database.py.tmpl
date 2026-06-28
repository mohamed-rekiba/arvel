"""Database test — the migrations apply and the User model + factory work, on in-memory sqlite.

Uses a standalone in-memory connection (shared pool), so it runs out of the box with no DB to set up.
"""

import pytest

from arvel.database import ConnectionResolver, Migrator, discover_migrations

from app.models.user import User
from database.factories.user_factory import UserFactory


@pytest.fixture
async def db() -> ConnectionResolver:
    resolver = ConnectionResolver()  # in-memory sqlite, shared across connections
    User.set_connection(resolver)
    await Migrator(resolver).run(discover_migrations(["database/migrations"]))
    return resolver


async def test_migrations_apply_and_factory_persists(db: ConnectionResolver) -> None:
    user = await UserFactory().create(name="Ada Lovelace", email="ada@example.com")
    assert user.name == "Ada Lovelace"
    assert len(await User.all()) == 1
