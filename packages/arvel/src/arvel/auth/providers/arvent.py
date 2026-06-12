"""ArventUserProvider — ORM-backed UserResolver."""

from __future__ import annotations

from typing import Any


def _coerce_pk(value: str) -> int | str:
    """Cast a numeric PK string to int so integer-PK models match on find()."""
    return int(value) if value.isdigit() else value


class ArventUserProvider:
    """Resolves users from an Arvent model class.

    Arvent is Arvel's ORM (the Eloquent-equivalent layer on top of SQLAlchemy).
    This provider resolves whichever `Model` subclass the app configures as the
    user model.
    """

    def __init__(
        self,
        *,
        model: type[Any],
        username_field: str = "email",
    ) -> None:
        self._model = model
        self._username_field = username_field

    async def by_id(self, user_id: str) -> Any | None:
        # Route through find()/where() so global scopes (soft-delete, tenant, …)
        # apply — a raw select() would let trashed users authenticate, diverging
        # from AuthService and Laravel's EloquentUserProvider.
        return await self._model.find(_coerce_pk(user_id))

    async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
        username = credentials.get(self._username_field)
        if username is None or getattr(self._model, self._username_field, None) is None:
            return None
        # Normalize string usernames (email addresses) so "User@Example.COM"
        # matches "user@example.com" in the database — mirrors Laravel's
        # EloquentUserProvider which lowercases before the query.
        if isinstance(username, str):
            username = username.strip().lower()
        return await self._model.where(**{self._username_field: username}).first()
