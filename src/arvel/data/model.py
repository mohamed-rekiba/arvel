"""ArvelModel — SA DeclarativeBase with auto-generated Pydantic schema.

Extends SQLAlchemy's DeclarativeBase. A __init_subclass__ hook introspects
SA Mapped[] annotations and builds a Pydantic BaseModel for validation
and serialization (model_validate / model_dump).

Includes the HasRelationships mixin for declarative relationship helpers
(has_one, has_many, belongs_to, belongs_to_many).
"""

from __future__ import annotations

import contextlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar, Self

from pydantic import BaseModel, create_model  # noqa: TC002
from sqlalchemy import DateTime, Table
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column  # noqa: TC002

from arvel.data._mass_assign import filter_mass_assignable
from arvel.data.accessors import _discover_accessors
from arvel.data.casts import resolve_caster
from arvel.data.exceptions import (
    ConfigurationError,
    CreationAbortedError,
    DeletionAbortedError,
    NotFoundError,
    UpdateAbortedError,
)
from arvel.data.query import QueryBuilder
from arvel.data.relationships.mixin import HasRelationships
from arvel.data.scopes import _discover_scopes
from arvel.logging import Log

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.elements import ColumnElement

    from arvel.data.accessors import AccessorRegistry
    from arvel.data.casts import Caster
    from arvel.data.collection import ArvelCollection
    from arvel.data.observer import ObserverRegistry
    from arvel.data.scopes import ScopeRegistry

_logger = Log.named("arvel.data.model")

_SA_TYPE_MAP: dict[str, type] = {
    "INTEGER": int,
    "BIGINT": int,
    "SMALLINT": int,
    "FLOAT": float,
    "DOUBLE": float,
    "DOUBLE_PRECISION": float,
    "REAL": float,
    "NUMERIC": Decimal,
    "DECIMAL": Decimal,
    "STRING": str,
    "VARCHAR": str,
    "CHAR": str,
    "TEXT": str,
    "CLOB": str,
    "NVARCHAR": str,
    "NCHAR": str,
    "UNICODE": str,
    "UNICODE_TEXT": str,
    "BOOLEAN": bool,
    "DATETIME": datetime,
    "TIMESTAMP": datetime,
    "DATE": date,
    "TIME": time,
    "JSON": dict,
    "JSONB": dict,
    "BLOB": bytes,
    "LARGEBINARY": bytes,
    "VARBINARY": bytes,
    "UUID": str,
    "ENUM": str,
    "ARRAY": list,
    "INTERVAL": float,
}


def _python_type_for_column(col: Any) -> type:
    """Extract the Python type from a SA column's type annotation.

    Tries the SA type's ``python_type`` first. Falls back to a name-based
    lookup in ``_SA_TYPE_MAP`` for SA types that don't implement
    ``python_type`` (e.g. ``JSON``).
    """
    try:
        return col.type.python_type
    except NotImplementedError:
        pass

    type_name = type(col.type).__name__.upper()
    return _SA_TYPE_MAP.get(type_name, str)


def _json_serial(obj: Any) -> Any:
    """JSON serializer for types not serializable by default."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (date, time)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    msg = f"Object of type {type(obj).__name__} is not JSON serializable"
    raise TypeError(msg)


class ArvelModel(HasRelationships, DeclarativeBase):
    """Base model class bridging SQLAlchemy and Pydantic.

    Subclasses get automatic:
    - SA table mapping (via DeclarativeBase)
    - Pydantic schema generation (__pydantic_model__)
    - Timestamp fields (created_at, updated_at) when declared
    - model_dump() / model_validate() compatibility
    - Declarative relationship helpers via HasRelationships

    Set ``__singular__`` on models with irregular plural table names so
    convention-based FK inference works correctly::

        class Person(ArvelModel):
            __tablename__ = "people"
            __singular__ = "person"
    """

    __abstract__ = True
    __pydantic_model__: ClassVar[type[BaseModel]]
    __fillable__: ClassVar[set[str] | None]
    __guarded__: ClassVar[set[str] | None]
    __casts__: ClassVar[dict[str, str | type | Caster]]
    __hidden__: ClassVar[set[str]]
    __visible__: ClassVar[set[str]]
    __appends__: ClassVar[set[str]]
    __scope_registry__: ClassVar[ScopeRegistry]
    __accessor_registry__: ClassVar[AccessorRegistry]
    _resolved_casts: ClassVar[dict[str, Caster]]
    _has_casts: ClassVar[bool]
    _column_names: ClassVar[frozenset[str]]
    _session_resolver: ClassVar[Callable[[], AsyncSession] | None] = None
    _session_factory_resolver: ClassVar[Callable[[], AsyncSession] | None] = None
    _observer_registry_resolver: ClassVar[Callable[[], ObserverRegistry] | None] = None

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        if cls.__dict__.get("__abstract__"):
            super().__init_subclass__(**kwargs)
            return

        if "__tablename__" not in cls.__dict__:
            cls.__tablename__ = cls._derive_tablename()

        cls._validate_mass_assignment()
        super().__init_subclass__(**kwargs)
        cls._build_pydantic_model()
        cls.__scope_registry__ = _discover_scopes(cls)
        cls.__accessor_registry__ = _discover_accessors(cls)
        cls._resolve_cast_definitions()
        cls._cache_column_names()
        cls._init_serialization_defaults()

    @classmethod
    def _derive_tablename(cls) -> str:
        """Derive table name from class name like Laravel: User -> users, BlogPost -> blog_posts."""
        from arvel.support.utils import pluralize, to_snake_case

        return pluralize(to_snake_case(cls.__name__))

    @classmethod
    def _resolve_cast_definitions(cls) -> None:
        """Resolve ``__casts__`` specs into ``Caster`` instances."""
        raw: dict[str, str | type | Caster] = getattr(cls, "__casts__", {})
        cls._resolved_casts = {name: resolve_caster(spec) for name, spec in raw.items()}
        cls._has_casts = bool(cls._resolved_casts)

    @classmethod
    def _cache_column_names(cls) -> None:
        """Cache column names for fast __getattribute__/__setattr__ checks."""
        table = getattr(cls, "__table__", None)
        if table is not None:
            cls._column_names = frozenset(col.name for col in table.columns)
        else:
            cls._column_names = frozenset()

    @classmethod
    def _init_serialization_defaults(cls) -> None:
        """Ensure __hidden__, __visible__, __appends__ are set on every subclass."""
        if "__hidden__" not in cls.__dict__:
            cls.__hidden__ = set()
        if "__visible__" not in cls.__dict__:
            cls.__visible__ = set()
        if "__appends__" not in cls.__dict__:
            cls.__appends__ = set()

    @classmethod
    def _validate_mass_assignment(cls) -> None:
        has_fillable = cls.__dict__.get("__fillable__") is not None
        has_guarded = cls.__dict__.get("__guarded__") is not None
        if has_fillable and has_guarded:
            msg = (
                f"{cls.__name__} defines both __fillable__ and __guarded__. "
                f"Use one or the other, not both."
            )
            raise ConfigurationError(msg)

    @classmethod
    def _build_pydantic_model(cls) -> None:
        """Auto-generate a Pydantic BaseModel from SA column definitions.

        All fields default to ``None`` so that partial data is accepted
        (matching Laravel Eloquent's create() semantics).  The database
        enforces NOT NULL constraints at insert time.
        """
        fields: dict[str, Any] = {}
        table = getattr(cls, "__table__", None)
        if table is None:
            return

        for col in table.columns:
            py_type = _python_type_for_column(col)
            fields[col.name] = (py_type | None, None)

        cls.__pydantic_model__ = create_model(
            f"{cls.__name__}Schema",
            **fields,
        )

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> Self:
        """Validate data through the auto-generated Pydantic schema, then create an instance."""
        validated = cls.__pydantic_model__.model_validate(data)
        validated_dict = validated.model_dump(exclude_unset=True)
        return cls(**validated_dict)

    def __getattribute__(self, name: str) -> Any:
        """Transparent cast on read + accessor resolution.

        For cast columns, the raw SA value is transformed through the
        caster's ``get()`` on every attribute access — no manual
        ``get_cast_value()`` needed.

        Models without ``__casts__`` skip the cast-check branch entirely.
        """
        cls = type(self)

        if cls.__dict__.get("_has_casts"):
            casts: dict[str, Caster] = cls.__dict__.get("_resolved_casts") or {}
            columns: frozenset[str] = cls.__dict__.get("_column_names") or frozenset()
            if name in casts and name in columns:
                raw = super().__getattribute__(name)
                return casts[name].get(raw, name, self)

        try:
            return super().__getattribute__(name)
        except AttributeError:
            pass

        registry: AccessorRegistry | None = cls.__dict__.get("__accessor_registry__")
        if registry is not None:
            acc_fn = registry.get_accessor(name)
            if acc_fn is not None:
                return acc_fn(self)
        raise AttributeError(f"'{cls.__name__}' has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        """Transparent cast on write + mutator integration.

        For cast columns, the value is transformed through the caster's
        ``set()`` before storage. Mutators run before casts.
        """
        cls = type(self)

        registry: AccessorRegistry | None = cls.__dict__.get("__accessor_registry__")
        if registry is not None:
            mut_fn = registry.get_mutator(name)
            if mut_fn is not None:
                value = mut_fn(self, value)

        if cls.__dict__.get("_has_casts"):
            casts: dict[str, Caster] = cls.__dict__.get("_resolved_casts") or {}
            columns: frozenset[str] = cls.__dict__.get("_column_names") or frozenset()
            if name in casts and name in columns:
                value = casts[name].set(value, name, self)

        super().__setattr__(name, value)

    def get_cast_value(self, attr_name: str) -> Any:
        """Explicitly get a column value with its cast applied.

        With transparent casting, this is equivalent to ``getattr(self, attr_name)``
        for cast columns. Kept for backward compatibility.
        """
        return getattr(self, attr_name)

    # ──── Serialization ────

    def make_hidden(self, *fields: str) -> Self:
        """Hide additional fields on this instance (does not affect the class)."""
        hidden: set[str] = getattr(self, "_instance_hidden", set())
        hidden = hidden | set(fields)
        object.__setattr__(self, "_instance_hidden", hidden)
        return self

    def make_visible(self, *fields: str) -> Self:
        """Un-hide fields on this instance (does not affect the class)."""
        visible: set[str] = getattr(self, "_instance_visible", set())
        visible = visible | set(fields)
        object.__setattr__(self, "_instance_visible", visible)
        return self

    def _effective_hidden(self) -> set[str]:
        """Compute the effective hidden set for this instance."""
        cls = type(self)
        class_hidden: set[str] = getattr(cls, "__hidden__", set())
        inst_hidden: set[str] = getattr(self, "_instance_hidden", set())
        inst_visible: set[str] = getattr(self, "_instance_visible", set())
        return (class_hidden | inst_hidden) - inst_visible

    def _effective_visible(self) -> set[str]:
        """Compute the effective visible set (whitelist mode) for this instance."""
        cls = type(self)
        return set(getattr(cls, "__visible__", set()))

    def model_dump(
        self,
        *,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
        include_relations: bool | list[str] = False,
    ) -> dict[str, Any]:
        """Serialize the model instance to a dict.

        Respects ``__hidden__``, ``__visible__``, ``__appends__``,
        and instance-level ``make_hidden()`` / ``make_visible()`` overrides.

        - ``__visible__`` is a whitelist — if set, ONLY those fields appear
        - ``__hidden__`` is a blacklist — those fields are excluded
        - ``__appends__`` adds accessor-computed values automatically
        - Cast values use their Python-side representations (via __getattribute__)
        """
        result = self._dump_columns(include=include, exclude=exclude)
        self._apply_serialization_control(result)
        self._apply_appended_accessors(result, include=include)
        if include_relations:
            self._dump_relations(result, include_relations)
        return result

    def __repr__(self) -> str:
        cls = type(self)
        table = getattr(cls, "__table__", None)
        if table is None:
            return f"<{cls.__name__}>"
        pk_cols = [col.name for col in table.primary_key.columns]
        pk_parts = [f"{name}={getattr(self, name, '?')!r}" for name in pk_cols]
        return f"<{cls.__name__} {' '.join(pk_parts)}>"

    def __str__(self) -> str:
        return self.model_json()

    def model_json(
        self,
        *,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
        include_relations: bool | list[str] = False,
    ) -> str:
        """Serialize the model instance to a JSON string.

        Convenience wrapper around ``model_dump()`` with JSON encoding
        of non-serializable types (datetime, date, Decimal, etc.).
        """
        data = self.model_dump(
            include=include,
            exclude=exclude,
            include_relations=include_relations,
        )
        return json.dumps(data, default=_json_serial)

    def _dump_columns(
        self,
        *,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        table = self.__class__.__table__
        for col in table.columns:
            name = col.name
            if include is not None and name not in include:
                continue
            if exclude is not None and name in exclude:
                continue
            result[name] = getattr(self, name, None)
        return result

    def _apply_serialization_control(self, result: dict[str, Any]) -> None:
        """Apply __hidden__ / __visible__ filtering."""
        visible = self._effective_visible()
        if visible:
            for key in list(result.keys()):
                if key not in visible:
                    del result[key]
            return

        hidden = self._effective_hidden()
        if hidden:
            for key in list(result.keys()):
                if key in hidden:
                    del result[key]

    def _apply_appended_accessors(
        self,
        result: dict[str, Any],
        *,
        include: set[str] | None = None,
    ) -> None:
        """Add accessor values from __appends__ and explicitly included names."""
        cls = type(self)
        appends: set[str] = getattr(cls, "__appends__", set())
        registry: AccessorRegistry | None = cls.__dict__.get("__accessor_registry__")
        if registry is None:
            return

        names_to_add = set(appends)
        if include is not None:
            names_to_add |= include & registry.accessor_names()

        for acc_name in names_to_add:
            with contextlib.suppress(AttributeError):
                result[acc_name] = getattr(self, acc_name)

    def _dump_relations(
        self,
        result: dict[str, Any],
        include_relations: bool | list[str],
    ) -> None:
        registry = getattr(self.__class__, "__relationship_registry__", None)
        if registry is None:
            return

        if include_relations is True:
            rel_names = list(registry.all().keys())
        elif isinstance(include_relations, list):
            rel_names = list(include_relations)
        else:
            return

        for rel_name in rel_names:
            value = getattr(self, rel_name, None)
            if value is None:
                result[rel_name] = None
            elif isinstance(value, list):
                result[rel_name] = [
                    item.model_dump() if hasattr(item, "model_dump") else item for item in value
                ]
            elif hasattr(value, "model_dump"):
                result[rel_name] = value.model_dump()
            else:
                result[rel_name] = value

    # ──── Session resolver ────

    @classmethod
    def set_session_resolver(cls, resolver: Callable[[], AsyncSession]) -> None:
        """Set the default session resolver for all models.

        Called by ``DatabaseServiceProvider`` during boot so that
        ``Model.query()`` works without an explicit session.
        """
        cls._session_resolver = resolver

    @classmethod
    def set_session_factory(cls, factory: Callable[[], AsyncSession]) -> None:
        """Set a factory that creates auto-managed sessions for CRUD ops.

        Unlike ``set_session_resolver``, sessions from this factory are
        committed on success and closed on exit by ``_session_scope``.
        """
        cls._session_factory_resolver = factory

    @classmethod
    def clear_session_resolver(cls) -> None:
        """Remove the default session resolver and factory."""
        cls._session_resolver = None
        cls._session_factory_resolver = None

    @classmethod
    def _resolve_session(cls, session: AsyncSession | None = None) -> AsyncSession:
        """Return the given session, or resolve one from the provider."""
        if session is not None:
            return session
        if cls._session_resolver is not None:
            return cls._session_resolver()
        msg = (
            "No session provided and no default session resolver is configured. "
            "Either pass a session explicitly or register "
            "DatabaseServiceProvider in your bootstrap/providers.py."
        )
        raise RuntimeError(msg)

    @classmethod
    @asynccontextmanager
    async def _session_scope(
        cls, session: AsyncSession | None = None
    ) -> AsyncGenerator[AsyncSession]:
        """Yield a session that auto-commits when it was created internally.

        Resolution order:
        1. *session* provided by caller → yield as-is (caller owns lifecycle).
        2. ``_session_factory_resolver`` set → create a fresh session, commit
           on success, rollback + close on failure.  This is the production
           path (``DatabaseServiceProvider`` sets the factory).
        3. ``_session_resolver`` set → yield the resolver's session without
           commit/close (backward compat with test fixtures that manage
           their own transactions).
        """
        if session is not None:
            yield session
            return

        if cls._session_factory_resolver is not None:
            owned = cls._session_factory_resolver()
            try:
                yield owned
                await owned.commit()
            except BaseException:
                await owned.rollback()
                raise
            finally:
                await owned.close()
            return

        yield cls._resolve_session()

    # ──── Observer registry resolver ────

    @classmethod
    def set_observer_registry(cls, resolver: Callable[[], ObserverRegistry]) -> None:
        """Set the default observer registry resolver for all models."""
        cls._observer_registry_resolver = resolver

    @classmethod
    def clear_observer_registry(cls) -> None:
        """Remove the default observer registry resolver."""
        cls._observer_registry_resolver = None

    @classmethod
    def _resolve_observer_registry(cls) -> ObserverRegistry:
        """Return the observer registry, or an empty no-op one."""
        if cls._observer_registry_resolver is not None:
            return cls._observer_registry_resolver()
        from arvel.data.observer import ObserverRegistry as _ObserverRegistry

        return _ObserverRegistry()

    # ──── Query builder entry ────

    @classmethod
    def query(cls, session: AsyncSession | None = None) -> QueryBuilder[Self]:
        """Create a fluent query builder.

        When *session* is omitted, uses the resolver set by
        ``DatabaseServiceProvider``.  Pass an explicit session to
        override (useful in tests or transactions).
        """
        if session is not None:
            return QueryBuilder(cls, session, owns_session=False)
        if cls._session_factory_resolver is not None:
            return QueryBuilder(cls, cls._session_factory_resolver(), owns_session=True)
        return QueryBuilder(cls, cls._resolve_session(), owns_session=False)

    # ──── Helpers ────

    @classmethod
    def _pk_column(cls) -> Any:
        """Return the single PK column for this model."""
        table = cls.__table__
        if not isinstance(table, Table):
            msg = f"{cls.__name__}.__table__ is not a Table"
            raise TypeError(msg)
        pk_cols = list(table.primary_key.columns)
        if len(pk_cols) != 1:
            msg = f"{cls.__name__} must have exactly one PK column"
            raise TypeError(msg)
        return pk_cols[0]

    def _is_new(self) -> bool:
        """Whether this instance has never been persisted (transient)."""
        state = sa_inspect(self, raiseerr=False)
        if state is None:
            return True
        return state.transient or state.pending

    # ──── Static query shortcuts ────

    @classmethod
    def where(
        cls, *criteria: ColumnElement[bool], session: AsyncSession | None = None
    ) -> QueryBuilder[Self]:
        """Shortcut for ``Model.query().where(...)``."""
        return cls.query(session).where(*criteria)

    @classmethod
    async def first(cls, *, session: AsyncSession | None = None) -> Self | None:
        """Return the first record or ``None``."""
        pk = cls._pk_column()
        return await cls.query(session).order_by(pk).first()

    @classmethod
    async def last(cls, *, session: AsyncSession | None = None) -> Self | None:
        """Return the last record (by PK descending) or ``None``."""
        pk = cls._pk_column()
        return await cls.query(session).order_by(pk.desc()).first()

    @classmethod
    async def count(cls, *, session: AsyncSession | None = None) -> int:
        """Return the total record count."""
        return await cls.query(session).count()

    # ──── CRUD: find ────

    @classmethod
    async def find(cls, record_id: int | str, *, session: AsyncSession | None = None) -> Self:
        """Find a record by primary key or raise ``NotFoundError``."""
        pk = cls._pk_column()
        instance = await cls.query(session).where(pk == record_id).order_by(pk).first()
        if instance is None:
            raise NotFoundError(
                f"{cls.__name__} with id={record_id} not found",
                model_name=cls.__name__,
                record_id=record_id,
            )
        return instance

    @classmethod
    async def find_or_none(
        cls, record_id: int | str, *, session: AsyncSession | None = None
    ) -> Self | None:
        """Find a record by primary key, returning ``None`` if not found."""
        pk = cls._pk_column()
        return await cls.query(session).where(pk == record_id).order_by(pk).first()

    @classmethod
    async def find_many(
        cls, record_ids: Sequence[int | str], *, session: AsyncSession | None = None
    ) -> ArvelCollection[Self]:
        """Find multiple records by primary keys.

        Missing IDs are silently skipped — no error is raised.
        """
        if not record_ids:
            from arvel.data.collection import ArvelCollection

            return ArvelCollection()
        pk = cls._pk_column()
        return await cls.query(session).where(pk.in_(record_ids)).all()

    @classmethod
    async def all(cls, *, session: AsyncSession | None = None) -> ArvelCollection[Self]:  # type: ignore[override]
        """Retrieve all records."""
        return await cls.query(session).all()

    # ──── CRUD: create ────

    @classmethod
    async def create(cls, data: dict[str, Any], *, session: AsyncSession | None = None) -> Self:
        """Create a new record with mass-assignment protection and observer dispatch.

        Event order: saving → creating → INSERT → created → saved
        """
        async with cls._session_scope(session) as resolved:
            registry = cls._resolve_observer_registry()
            safe_data = filter_mass_assignable(cls, data)
            instance = cls.model_validate(safe_data)

            if not await registry.dispatch("saving", cls, instance):
                raise CreationAbortedError(
                    f"Save of {cls.__name__} aborted by observer",
                    model_name=cls.__name__,
                )
            if not await registry.dispatch("creating", cls, instance):
                raise CreationAbortedError(
                    f"Creation of {cls.__name__} aborted by observer",
                    model_name=cls.__name__,
                )

            resolved.add(instance)
            await resolved.flush()

            await registry.dispatch("created", cls, instance)
            await registry.dispatch("saved", cls, instance)
            return instance

    # ──── CRUD: update ────

    async def update(self, data: dict[str, Any], *, session: AsyncSession | None = None) -> Self:
        """Update this instance with observer dispatch.

        Event order: saving → updating → UPDATE → updated → saved
        """
        async with self._session_scope(session) as resolved:
            registry = self._resolve_observer_registry()
            model_cls = type(self)

            if not await registry.dispatch("saving", model_cls, self):
                raise UpdateAbortedError(
                    f"Save of {model_cls.__name__} aborted by observer",
                    model_name=model_cls.__name__,
                )
            if not await registry.dispatch("updating", model_cls, self):
                raise UpdateAbortedError(
                    f"Update of {model_cls.__name__} aborted by observer",
                    model_name=model_cls.__name__,
                )

            safe_data = filter_mass_assignable(model_cls, data)
            for key, value in safe_data.items():
                setattr(self, key, value)
            if hasattr(self, "updated_at"):
                self.updated_at = datetime.now(UTC)
            await resolved.flush()

            await registry.dispatch("updated", model_cls, self)
            await registry.dispatch("saved", model_cls, self)
            return self

    # ──── CRUD: save ────

    async def save(self, *, session: AsyncSession | None = None) -> Self:
        """Persist the current state of this instance.

        Detects new vs existing: fires creating/created for inserts,
        updating/updated for updates. Always fires saving/saved.
        """
        async with self._session_scope(session) as resolved:
            registry = self._resolve_observer_registry()
            model_cls = type(self)
            is_new = self._is_new()

            if not await registry.dispatch("saving", model_cls, self):
                raise (
                    CreationAbortedError(
                        f"Save of {model_cls.__name__} aborted by observer",
                        model_name=model_cls.__name__,
                    )
                    if is_new
                    else UpdateAbortedError(
                        f"Save of {model_cls.__name__} aborted by observer",
                        model_name=model_cls.__name__,
                    )
                )

            specific_event = "creating" if is_new else "updating"
            if not await registry.dispatch(specific_event, model_cls, self):
                if is_new:
                    raise CreationAbortedError(
                        f"Creation of {model_cls.__name__} aborted by observer",
                        model_name=model_cls.__name__,
                    )
                raise UpdateAbortedError(
                    f"Update of {model_cls.__name__} aborted by observer",
                    model_name=model_cls.__name__,
                )

            if hasattr(self, "updated_at"):
                self.updated_at = datetime.now(UTC)
            resolved.add(self)
            await resolved.flush()

            post_event = "created" if is_new else "updated"
            await registry.dispatch(post_event, model_cls, self)
            await registry.dispatch("saved", model_cls, self)
            return self

    # ──── CRUD: delete ────

    async def delete(self, *, session: AsyncSession | None = None) -> None:
        """Delete this instance with observer dispatch.

        If the model uses ``SoftDeletes``, sets ``deleted_at`` instead
        of removing the row.
        """
        from arvel.data.soft_deletes import is_soft_deletable

        async with self._session_scope(session) as resolved:
            registry = self._resolve_observer_registry()
            model_cls = type(self)

            if not await registry.dispatch("deleting", model_cls, self):
                raise DeletionAbortedError(
                    f"Deletion of {model_cls.__name__} aborted by observer",
                    model_name=model_cls.__name__,
                )

            if is_soft_deletable(model_cls):
                setattr(self, "deleted_at", datetime.now(UTC))  # noqa: B010
                await resolved.flush()
            else:
                await resolved.delete(self)
                await resolved.flush()

            await registry.dispatch("deleted", model_cls, self)

    # ──── CRUD: refresh ────

    async def refresh(self, *, session: AsyncSession | None = None) -> Self:
        """Reload this instance from the database."""
        async with self._session_scope(session) as resolved:
            await resolved.refresh(self)
            return self

    # ──── CRUD: fill ────

    def fill(self, data: dict[str, Any]) -> Self:
        """Mass-assign attributes without saving.

        Respects ``__fillable__`` / ``__guarded__`` protection.
        """
        safe_data = filter_mass_assignable(type(self), data)
        for key, value in safe_data.items():
            setattr(self, key, value)
        return self

    # ──── Convenience: first_or_create / first_or_new / update_or_create ────

    @classmethod
    async def first_or_create(
        cls,
        search: dict[str, Any],
        values: dict[str, Any] | None = None,
        *,
        session: AsyncSession | None = None,
    ) -> Self:
        """Find a matching record or create one.

        *search* fields are used to find; *values* are merged when creating.
        Observer events fire on creation.
        """
        async with cls._session_scope(session) as resolved_session:
            q = cls.query(resolved_session)
            pk = cls._pk_column()
            for key, value in search.items():
                col = getattr(cls, key, None)
                if col is not None:
                    q = q.where(col == value)
            existing = await q.order_by(pk).first()
            if existing is not None:
                return existing
            merged = {**search, **(values or {})}
            return await cls.create(merged, session=resolved_session)

    @classmethod
    def first_or_new(
        cls,
        search: dict[str, Any],
        values: dict[str, Any] | None = None,
    ) -> Self:
        """Build a new (unsaved) instance from search + values.

        Does NOT persist. Does NOT query the database.
        Use ``first_or_create`` if you need to check the DB first.
        """
        merged = {**search, **(values or {})}
        safe_data = filter_mass_assignable(cls, merged)
        return cls.model_validate(safe_data)

    @classmethod
    async def update_or_create(
        cls,
        search: dict[str, Any],
        values: dict[str, Any] | None = None,
        *,
        session: AsyncSession | None = None,
    ) -> Self:
        """Find a matching record and update it, or create a new one.

        Observer events fire for both update and create paths.
        """
        async with cls._session_scope(session) as resolved_session:
            q = cls.query(resolved_session)
            pk = cls._pk_column()
            for key, value in search.items():
                col = getattr(cls, key, None)
                if col is not None:
                    q = q.where(col == value)
            existing = await q.order_by(pk).first()
            if existing is not None:
                return await existing.update(values or {}, session=resolved_session)
            merged = {**search, **(values or {})}
            return await cls.create(merged, session=resolved_session)

    # ──── Convenience: destroy ────

    @classmethod
    async def destroy(
        cls,
        record_ids: int | str | Sequence[int | str],
        *,
        session: AsyncSession | None = None,
    ) -> int:
        """Delete one or more records by primary key.

        Returns the number of records deleted. Fires observer events
        for each record.
        """
        async with cls._session_scope(session) as resolved_session:
            if isinstance(record_ids, (int, str)):
                record_ids = [record_ids]
            instances = await cls.find_many(record_ids, session=resolved_session)
            for instance in instances:
                await instance.delete(session=resolved_session)
            return len(instances)
