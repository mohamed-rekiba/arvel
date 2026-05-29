"""UserFactory — generate fake User instances for tests and seeders."""

from __future__ import annotations

import uuid

from app.models.user import User
from arvel.database import Factory
from faker import Faker

fake = Faker()


class UserFactory(Factory[User]):
    """Default User factory.

    Usage::

        # Build one unsaved instance
        user = UserFactory().make()

        # Save one user to DB (inside an async test)
        user = await UserFactory().create()

        # Create 10 users
        users = await UserFactory().count(10).create()

        # Override specific fields
        admin = await UserFactory().state({"role": "admin"}).create()
    """

    model = User

    def definition(self) -> dict:
        return {
            "id": str(uuid.uuid7()),
            "name": fake.name(),
            "email": fake.unique.email(),
            "password": fake.sha256(),
        }
