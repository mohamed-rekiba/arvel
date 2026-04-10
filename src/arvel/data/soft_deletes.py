"""Soft-delete mixin for ArvelModel.

Adds a ``deleted_at`` timestamp column. When mixed into a model, the
default ``Repository.delete()`` sets the timestamp instead of issuing a
SQL DELETE, and all queries automatically exclude soft-deleted rows via
a global scope.

Usage::

    class Post(SoftDeletes, ArvelModel):
        __tablename__ = "posts"
        id: Mapped[int] = mapped_column(primary_key=True)
        title: Mapped[str] = mapped_column(String(200))
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.scopes import GlobalScope

if TYPE_CHECKING:
    from arvel.data.query import QueryBuilder

_SOFT_DELETE_ATTR = "__soft_deletes__"


class _SoftDeleteScope(GlobalScope):
    """Global scope that excludes soft-deleted rows."""

    name = "SoftDeleteScope"

    def __init__(self, model_cls: type) -> None:
        self._model_cls = model_cls

    def apply(self, query: QueryBuilder[Any]) -> QueryBuilder[Any]:
        deleted_at_col = getattr(self._model_cls, "deleted_at")  # noqa: B009  # dynamic: SoftDeletes mixin adds this column
        return query.where(deleted_at_col.is_(None))


class SoftDeletes:
    """Mixin that adds soft-delete behavior to an ArvelModel subclass.

    Declares ``deleted_at: Mapped[datetime | None]`` and registers a
    global scope that filters out soft-deleted rows.

    The ``Repository`` checks for this mixin at runtime and redirects
    ``delete()`` to set ``deleted_at`` instead of issuing a hard DELETE.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        if not cls.__dict__.get("__abstract__") and hasattr(cls, "__tablename__"):
            setattr(cls, _SOFT_DELETE_ATTR, True)
            _register_soft_delete_scope(cls)
        super().__init_subclass__(**kwargs)

    @property
    def trashed(self) -> bool:
        """Whether this instance is soft-deleted."""
        return self.deleted_at is not None


@lru_cache(maxsize=128)
def is_soft_deletable(model_cls: type) -> bool:
    """Check if a model class uses the SoftDeletes mixin.

    Cached per class — the ``__soft_deletes__`` flag is set once in ``__init_subclass__``.
    """
    return getattr(model_cls, _SOFT_DELETE_ATTR, False) is True


def _register_soft_delete_scope(cls: type) -> None:
    """Attach the SoftDeleteScope to the model's global scopes."""
    existing = getattr(cls, "__global_scopes__", [])
    scope_instance = _SoftDeleteScope(cls)
    setattr(cls, "__global_scopes__", [*existing, scope_instance])  # noqa: B010
