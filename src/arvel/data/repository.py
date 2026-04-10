"""Generic typed repository with CRUD operations.

Encapsulates all SQLAlchemy session usage. Services and controllers
never touch the session directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from types import get_original_bases
from typing import TYPE_CHECKING, Any, cast, get_args

from sqlalchemy import Table, select

from arvel.data._mass_assign import filter_mass_assignable
from arvel.data.exceptions import (
    CreationAbortedError,
    DeletionAbortedError,
    NotFoundError,
    UpdateAbortedError,
)
from arvel.data.query import QueryBuilder

if TYPE_CHECKING:
    from sqlalchemy import Column
    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.data.collection import ArvelCollection
    from arvel.data.model import ArvelModel
    from arvel.data.observer import ObserverRegistry


@lru_cache(maxsize=64)
def _resolve_model_type(repo_cls: type) -> type:
    """Extract T from Repository[T] via generic introspection.

    Cached per repository class — the generic parameter is fixed at class definition.
    """
    for base in get_original_bases(repo_cls):
        args = get_args(base)
        if args and isinstance(args[0], type):
            return args[0]
    for base in repo_cls.__mro__:
        for orig_base in getattr(base, "__orig_bases__", ()):
            args = get_args(orig_base)
            if args and isinstance(args[0], type):
                return args[0]
    msg = f"Cannot resolve model type for {repo_cls.__name__}"
    raise TypeError(msg)


class Repository[T: "ArvelModel"]:
    """Base repository providing typed CRUD operations.

    The session is private — custom query methods use ``self.query()``
    which returns a ``QueryBuilder[T]``, not the raw session.

    When ``DatabaseServiceProvider`` is registered, both *session* and
    *observer_registry* are optional — the repository resolves them
    from the model's session resolver and creates an empty registry::

        repo = UserRepository()  # uses default session
        repo = UserRepository(session=my_session)  # explicit override
    """

    def __init__(
        self,
        *,
        session: AsyncSession | None = None,
        observer_registry: ObserverRegistry | None = None,
    ) -> None:
        if session is None:
            from arvel.data.model import ArvelModel

            resolver = ArvelModel._session_resolver
            if resolver is None:
                msg = (
                    "No session provided and no default session resolver is configured. "
                    "Either pass a session explicitly or register "
                    "DatabaseServiceProvider in your bootstrap/providers.py."
                )
                raise RuntimeError(msg)
            session = resolver()

        if observer_registry is None:
            from arvel.data.observer import ObserverRegistry as _ObserverRegistry

            observer_registry = _ObserverRegistry()

        self._session = session
        self._observer_registry = observer_registry
        # Sound cast: _resolve_model_type walks __orig_bases__ to find the concrete T
        self._model_cls: type[T] = cast("type[T]", _resolve_model_type(type(self)))

    @property
    def _pk_column(self) -> Column[Any]:
        """Return the primary key column from the model's table."""
        table = self._model_cls.__table__
        if not isinstance(table, Table):
            msg = f"{self._model_cls.__name__}.__table__ is not a Table"
            raise TypeError(msg)
        pk_cols = list(table.primary_key.columns)
        if len(pk_cols) != 1:
            msg = (
                f"{self._model_cls.__name__} must have exactly one PK column for Repository.find()"
            )
            raise TypeError(msg)
        return pk_cols[0]

    def query(self) -> QueryBuilder[T]:
        return QueryBuilder(self._model_cls, self._session)

    async def find(self, record_id: int | str) -> T:
        instance = (
            await self.query().where(self._pk_column == record_id).order_by(self._pk_column).first()
        )
        if instance is None:
            raise NotFoundError(
                f"{self._model_cls.__name__} with id={record_id} not found",
                model_name=self._model_cls.__name__,
                record_id=record_id,
            )
        return instance

    async def all(self) -> ArvelCollection[T]:
        return await self.query().all()

    async def create(self, data: dict[str, Any]) -> T:
        safe_data = filter_mass_assignable(self._model_cls, data)
        instance = self._model_cls.model_validate(safe_data)

        allowed = await self._observer_registry.dispatch("creating", self._model_cls, instance)
        if not allowed:
            raise CreationAbortedError(
                f"Creation of {self._model_cls.__name__} aborted by observer",
                model_name=self._model_cls.__name__,
            )

        self._session.add(instance)
        await self._session.flush()

        await self._observer_registry.dispatch("created", self._model_cls, instance)
        return instance

    async def update(self, record_id: int | str, data: dict[str, Any]) -> T:
        instance = await self.find(record_id)

        allowed = await self._observer_registry.dispatch("updating", self._model_cls, instance)
        if not allowed:
            raise UpdateAbortedError(
                f"Update of {self._model_cls.__name__} aborted by observer",
                model_name=self._model_cls.__name__,
            )

        safe_data = filter_mass_assignable(self._model_cls, data)
        for key, value in safe_data.items():
            setattr(instance, key, value)

        if hasattr(instance, "updated_at"):
            instance.updated_at = datetime.now(UTC)

        await self._session.flush()

        await self._observer_registry.dispatch("updated", self._model_cls, instance)
        return instance

    async def delete(self, record_id: int | str) -> None:
        from arvel.data.soft_deletes import is_soft_deletable

        instance = await self.find(record_id)

        allowed = await self._observer_registry.dispatch("deleting", self._model_cls, instance)
        if not allowed:
            raise DeletionAbortedError(
                f"Deletion of {self._model_cls.__name__} aborted by observer",
                model_name=self._model_cls.__name__,
            )

        if is_soft_deletable(self._model_cls):
            setattr(instance, "deleted_at", datetime.now(UTC))  # noqa: B010
            await self._session.flush()
        else:
            await self._session.delete(instance)
            await self._session.flush()

        await self._observer_registry.dispatch("deleted", self._model_cls, instance)

    async def restore(self, record_id: int | str) -> T:
        """Restore a soft-deleted record by setting ``deleted_at`` to NULL.

        Raises ``NotFoundError`` if the record doesn't exist.
        Only meaningful for models using the ``SoftDeletes`` mixin.
        """
        from arvel.data.soft_deletes import is_soft_deletable

        if not is_soft_deletable(self._model_cls):
            msg = f"{self._model_cls.__name__} does not support soft deletes"
            raise TypeError(msg)

        stmt = select(self._model_cls).where(self._pk_column == record_id)
        result = await self._session.execute(stmt)
        instance = result.scalars().first()
        if instance is None:
            raise NotFoundError(
                f"{self._model_cls.__name__} with id={record_id} not found",
                model_name=self._model_cls.__name__,
                record_id=record_id,
            )

        allowed = await self._observer_registry.dispatch("restoring", self._model_cls, instance)
        if not allowed:
            msg = f"Restore of {self._model_cls.__name__} aborted by observer"
            raise DeletionAbortedError(msg, model_name=self._model_cls.__name__)

        setattr(instance, "deleted_at", None)  # noqa: B010
        await self._session.flush()

        await self._observer_registry.dispatch("restored", self._model_cls, instance)
        return instance

    async def force_delete(self, record_id: int | str) -> None:
        """Permanently remove a record, bypassing soft deletes.

        Dispatches ``force_deleting``/``force_deleted`` observer events.
        """
        stmt = select(self._model_cls).where(self._pk_column == record_id)
        result = await self._session.execute(stmt)
        instance = result.scalars().first()
        if instance is None:
            raise NotFoundError(
                f"{self._model_cls.__name__} with id={record_id} not found",
                model_name=self._model_cls.__name__,
                record_id=record_id,
            )

        allowed = await self._observer_registry.dispatch(
            "force_deleting", self._model_cls, instance
        )
        if not allowed:
            raise DeletionAbortedError(
                f"Force deletion of {self._model_cls.__name__} aborted by observer",
                model_name=self._model_cls.__name__,
            )

        await self._session.delete(instance)
        await self._session.flush()

        await self._observer_registry.dispatch("force_deleted", self._model_cls, instance)
