"""User factory — generates fake users for tests and seeders."""

from typing import Any

from arvel.database import Factory

from app.models.user import User


class UserFactory(Factory[User]):
    model = User

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.faker.name(),
            "email": self.faker.unique.email(),
            "password": "password",  # the User model's `hashed` cast argon2-hashes this on save
        }
