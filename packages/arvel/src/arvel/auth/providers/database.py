"""DatabaseUserProvider — ORM-backed UserResolver."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from arvel.database.session import get_active_session


class DatabaseUserProvider:
    """Resolves users from an ORM Model class.

    Implements the UserResolver Protocol.
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
        session = get_active_session()
        pk_col = getattr(self._model, "id", None)
        if pk_col is None:
            return None
        result: Any = await session.execute(
            select(self._model).where(
                pk_col == int(user_id) if user_id.isdigit() else pk_col == user_id
            )
        )
        return result.scalars().first()

    async def by_credentials(self, credentials: dict[str, object]) -> Any | None:
        session = get_active_session()
        username = credentials.get(self._username_field)
        col = getattr(self._model, self._username_field, None)
        if col is None or username is None:
            return None
        result: Any = await session.execute(select(self._model).where(col == username))
        return result.scalars().first()
