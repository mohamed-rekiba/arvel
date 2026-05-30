"""``Model`` base + ``ActiveRecord`` / ``Timestamps`` / ``SoftDeletes`` mixins."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import InitVar
from datetime import UTC, date
from datetime import datetime as _datetime
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    TypeGuard,
    TypeVar,
    cast,
    dataclass_transform,
    get_origin,
)

from pydantic import BaseModel
from sqlalchemy import event, select
from sqlalchemy import inspect as sqla_inspect
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    MappedColumn,
    Mapper,
    RelationshipProperty,
    composite,
    deferred,
    mapped_column,
    relationship,
    synonym,
)
from sqlalchemy.orm.decl_api import DCTransformDeclarative

from arvel.database.columns import (
    big_integer,
    boolean,
    datetime,
    decimal,
    enum,
    foreign_id,
    foreign_uuid,
    id_,
    integer,
    json,
    jsonb,
    string,
    text,
    tsvector,
    uuid,
    uuid_id,
)
from arvel.database.exceptions import (
    CastError,
    MassAssignmentError,
    ModelNotFoundError,
    ReadOnlyModelError,
    RelationNotLoadedError,
)
from arvel.database.query_mixin import QueryMixin
from arvel.database.session import get_active_session
from arvel.support.str import Str

if TYPE_CHECKING:
    from arvel.database.orm.relations import BelongsTo, HasMany, HasOne

ModelT = TypeVar("ModelT", bound="Model")
RelatedT = TypeVar("RelatedT", bound="Model")
SchemaT = TypeVar("SchemaT", bound=BaseModel)


def _json_cast(value: Any) -> Any:
    """Decode ``value`` from JSON if it's a string, otherwise return as-is."""
    import json

    return json.loads(value) if isinstance(value, str) else value


def _to_utc_datetime(value: Any) -> _datetime:
    """Coerce ``value`` to a UTC-aware ``datetime``. Raises CastException on failure.

    Accepts ISO-8601 strings, ``datetime`` (naive treated as UTC, aware
    converted), and numeric epoch seconds.
    """
    if isinstance(value, _datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = _datetime.fromisoformat(value)
        except ValueError as exc:
            raise CastError("datetime", value, str(exc)) from exc
        return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return _datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise CastError("datetime", value, str(exc)) from exc
    raise CastError("datetime", value)


def _datetime_cast(value: Any) -> _datetime:
    return _to_utc_datetime(value)


def _date_cast(value: Any) -> date:
    # datetime is a date subclass — narrow that case before bare-date passthrough.
    if isinstance(value, _datetime):
        return _to_utc_datetime(value).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        # Try a pure date first (YYYY-MM-DD); fall back to ISO datetime → date.
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        return _to_utc_datetime(value).date()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _to_utc_datetime(value).date()
    raise CastError("date", value)


def _bool_cast(value: Any) -> bool:
    # Mirrors PHP's (bool) used by Laravel's boolean cast: the string "0" and ""
    # are False, every other non-empty string (including "false") is True.
    # Plain bool() would make bool("0") True, diverging from Laravel.
    if isinstance(value, str):
        return value not in ("", "0")
    return bool(value)


def _timestamp_cast(value: Any) -> int:
    if isinstance(value, bool):
        # bool is an int subclass — refuse explicitly so booleans don't become 0/1 epochs.
        raise CastError("timestamp", value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(_to_utc_datetime(value).timestamp())


# Dispatch table for __casts__ — maps a cast type name to a value coercer.
_CAST_DISPATCH: dict[str, Callable[[Any], Any]] = {
    "boolean": _bool_cast,
    "bool": _bool_cast,
    "integer": int,
    "int": int,
    "float": float,
    "string": str,
    "str": str,
    "dict": _json_cast,
    "list": _json_cast,
    "array": _json_cast,
    "datetime": _datetime_cast,
    "date": _date_cast,
    "timestamp": _timestamp_cast,
}
_VALID_CASTS: frozenset[str] = frozenset(_CAST_DISPATCH)

# JSON collection casts stay read-path only on write — coercing to dict/list in
# memory breaks String-column INSERTs. Use TypeDecorator for column-level JSON.
_WRITE_SKIP_CASTS: frozenset[str] = frozenset({"dict", "list", "array"})


def _should_auto_wrap(attr_name: str, annotation: Any, value: Any) -> bool:
    """Return True when the annotation should be wrapped with Mapped[T].

    Exclusions: already-Mapped, ClassVar, InitVar, dunder names, and values
    that are not MappedColumn / RelationshipProperty instances.
    """
    # Only wrap column/relationship descriptors
    if not isinstance(value, (MappedColumn, RelationshipProperty)):
        return False

    if isinstance(annotation, str):
        s = annotation.strip()
        # Already wrapped or is a special form
        return not s.startswith(("Mapped[", "ClassVar[", "ClassVar", "InitVar[", "InitVar"))

    origin = get_origin(annotation)
    if origin is Mapped or origin is ClassVar:
        return False
    if isinstance(annotation, InitVar):
        return False
    return True


_MappedAlias: Any = Mapped


@dataclass_transform(
    kw_only_default=True,
    field_specifiers=(
        MappedColumn,
        RelationshipProperty,
        mapped_column,
        relationship,
        composite,
        deferred,
        synonym,
        id_,
        uuid_id,
        big_integer,
        boolean,
        datetime,
        decimal,
        enum,
        foreign_id,
        foreign_uuid,
        integer,
        json,
        jsonb,
        string,
        text,
        tsvector,
        uuid,
    ),
)
class _ModelMeta(DCTransformDeclarative):
    """Metaclass for Arvel ORM models (SQLAlchemy DeclarativeBase + dataclass_transform).

    Auto-wraps plain type annotations with ``Mapped[T]`` when the assigned
    value is a ``MappedColumn`` or ``RelationshipProperty``. This lets models
    use plain annotations instead of the SQLAlchemy ``Mapped[T]`` wrapper::

        # Plain annotation (recommended)
        id: int = id_()
        name: str = string(255)

        # Also accepted (framework mixins use this style)
        id: Mapped[int] = id_()

    Resolves ``Post.active()`` to a ``scope_active`` method when the class
    has one (Laravel-style local-scope auto-discovery).
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        annotations: dict[str, Any] = namespace.get("__annotations__", {})
        new_annotations: dict[str, Any] = {}
        needs_mapped_in_module = False

        module_name: str = namespace.get("__module__", "")

        for attr_name, annotation in annotations.items():
            value = namespace.get(attr_name)
            if not _should_auto_wrap(attr_name, annotation, value):
                new_annotations[attr_name] = annotation
                continue

            if isinstance(annotation, str):
                # Build "Mapped[<annotation>]" as a string; SQLAlchemy's own
                # get_type_hints() resolver evaluates it using module globals.
                # We ensure Mapped is resolvable in that module below.
                new_annotations[attr_name] = f"Mapped[{annotation}]"
                needs_mapped_in_module = True
            else:
                # _MappedAlias typed as Any to avoid mypy's valid-type restriction on
                # subscripting a generic with a runtime variable.
                new_annotations[attr_name] = _MappedAlias[annotation]

        if new_annotations != annotations:
            namespace = {**namespace, "__annotations__": new_annotations}

        if needs_mapped_in_module and module_name:
            module = sys.modules.get(module_name)
            # Inject Mapped into module globals so get_type_hints() can resolve
            # "Mapped[str]" strings even when the model file doesn't import it.
            # This is safe: Mapped is a stable public SQLAlchemy type, and we
            # only add it when it isn't already present.
            if module is not None and not hasattr(module, "Mapped"):
                module.__dict__["Mapped"] = Mapped

        return super().__new__(mcs, name, bases, namespace, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # `self` here is the metaclass instance — i.e. the model class itself.
        model_cls: type[Any] = self
        scope_attr = f"scope_{name}"
        for klass in model_cls.__mro__:
            raw = vars(klass).get(scope_attr)
            if raw is not None:
                return _build_scope_class_caller(model_cls, raw)
        raise AttributeError(f"type object '{model_cls.__name__}' has no attribute '{name}'")


def _build_scope_class_caller(model_cls: type[Any], raw: Any) -> Any:
    """Wrap a ``scope_*`` method for class-level invocation (``Post.active()``).

    Auto-creates a fresh ``QueryBuilder`` and dispatches the scope method
    with the right ``self`` shape:
      - ``@staticmethod``  → call ``(query, *args, **kwargs)``
      - ``@classmethod``   → call ``(model_cls, query, *args, **kwargs)``
      - regular function   → call ``(model_cls.__new__(model_cls), query, *args, **kwargs)``
    """
    from arvel.database.query import QueryBuilder

    fn = unwrap_method(raw)

    if isinstance(raw, staticmethod):

        def static_call(*args: Any, **kwargs: Any) -> Any:
            return fn(QueryBuilder(model_cls), *args, **kwargs)

        return static_call

    if isinstance(raw, classmethod):

        def class_call(*args: Any, **kwargs: Any) -> Any:
            return fn(model_cls, QueryBuilder(model_cls), *args, **kwargs)

        return class_call

    def instance_call(*args: Any, **kwargs: Any) -> Any:
        # `object.__new__` skips SQLAlchemy's instrumented __init__ — fine for
        # scope dispatch since scope methods aren't supposed to touch DB state.
        instance = object.__new__(model_cls)
        return fn(instance, QueryBuilder(model_cls), *args, **kwargs)

    return instance_call


def unwrap_method(raw: Any) -> Callable[..., Any]:
    """Return the underlying function for a static/class method, or ``raw`` itself."""
    # Re-bind through `Any` so pyright doesn't narrow into `staticmethod[Unknown,...]`
    # where `__func__` carries unknown type parameters.
    boxed: Any = raw
    if isinstance(raw, (staticmethod, classmethod)):
        return cast("Callable[..., Any]", boxed.__func__)
    return cast("Callable[..., Any]", boxed)


def _check_mass_assignment(model_cls: type[Any], attrs: dict[str, Any]) -> None:
    """Enforce __fillable__ / __guarded__ on create()/update() calls."""
    fillable: list[str] | None = getattr(model_cls, "__fillable__", None)
    guarded: list[str] | None = getattr(model_cls, "__guarded__", None)

    if fillable is None and guarded is None:
        return  # no protection configured

    for key in attrs:
        if fillable is not None and key not in fillable:
            raise MassAssignmentError(model_cls.__name__, key)
        if guarded is not None and ("*" in guarded or key in guarded):
            raise MassAssignmentError(model_cls.__name__, key)


def _pk_name(model_cls: type[Any]) -> str:
    """Single-column primary-key attribute name for *model_cls* (Laravel's getKeyName)."""
    mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(model_cls))
    key = mapper.primary_key[0].key
    if key is None:
        raise TypeError(f"{model_cls.__name__} primary key column has no key")
    return key


def _is_pk_tuple(pk: object) -> TypeGuard[tuple[Any, ...]]:
    return isinstance(pk, tuple)


def _coerce_pk_to_tuple(pk: object) -> tuple[Any, ...]:
    """Normalise a primary-key value into a tuple suitable for composite-PK joins."""
    if _is_pk_tuple(pk):
        return pk
    return (pk,)


class ActiveRecord(QueryMixin):
    """Mixin that turns a SQLA declarative model into an ActiveRecord.

    Query entry points (``where``, ``order_by``, ``with_``, etc.) come from
    ``QueryMixin``. This class adds the terminal class-level operations
    (``find``, ``find_or_fail``, ``all``, ``create``) and instance-level
    persistence (``save``, ``delete``, ``fresh``, ``refresh``).
    """

    __fillable__: ClassVar[list[str] | None] = None
    __guarded__: ClassVar[list[str] | None] = None
    __hidden__: ClassVar[list[str] | None] = None
    __visible__: ClassVar[list[str] | None] = None
    # Accessor names appended to to_dict() output, like Eloquent's $appends.
    __appends__: ClassVar[list[str] | None] = None

    # Set per-instance at save time: column keys changed by the last save.
    _arvel_changed: ClassVar[frozenset[str] | None] = None

    # Column name -> mutator fn, collected from @mutator-decorated methods across
    # the MRO in __init_subclass__. Empty unless a subclass declares one.
    __arvel_mutators__: ClassVar[dict[str, Callable[[Any, Any], Any]]] = {}

    # Per-instance override set by make_hidden() / make_visible().
    # ClassVar keeps it out of MappedAsDataclass field processing and ORM column
    # mapping.  Instances get their own list via object.__setattr__ on first use.
    _instance_hidden: ClassVar[list[str] | None] = None

    @classmethod
    async def find(cls, pk: Any) -> Any:
        # Route through the query builder so global scopes (e.g. soft-delete)
        # are applied, and first() fires the retrieved event for us.
        mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(cls))
        pk_cols = mapper.primary_key
        if len(pk_cols) == 1:
            col_key = pk_cols[0].key
            if col_key is None:
                raise TypeError("Primary key column has no key")
            pk_attr = getattr(cls, col_key)
            return await cls.query().where(pk_attr == pk).first()
        # Composite PK: pk must be a tuple matching column order
        qb = cls.query()
        pk_values = _coerce_pk_to_tuple(pk)
        for col, val in zip(pk_cols, pk_values, strict=False):
            if col.key is None:
                raise TypeError("Primary key column has no key")
            qb = qb.where(getattr(cls, col.key) == val)
        return await qb.first()

    @classmethod
    async def find_or_fail(cls, pk: Any) -> Any:
        instance = await cls.find(pk)
        if instance is None:
            raise ModelNotFoundError(cls.__name__, pk)
        return instance

    @classmethod
    async def create(cls, **attrs: Any) -> Any:
        from arvel.database.events import fire_after_commit, fire_async, fire_cancellable

        _check_mass_assignment(cls, attrs)
        instance = cast("Any", cls)(**attrs)
        await fire_async(cls, "saving", instance)
        await fire_cancellable(cls, "creating", instance)
        session = get_active_session()
        session.add(instance)
        instance._arvel_snapshot_changes()
        await session.flush()
        await fire_async(cls, "created", instance)
        await fire_async(cls, "saved", instance)
        fire_after_commit(cls, instance)
        return instance

    def fill(self, **attrs: Any) -> Any:
        """Mass-assign attributes in place, honouring fillable/guarded and mutators."""
        _check_mass_assignment(type(self), attrs)
        for key, value in attrs.items():
            setattr(self, key, value)
        return self

    def _arvel_column_keys(self) -> list[str]:
        mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(type(self)))
        return [c.key for c in mapper.column_attrs]

    def is_dirty(self, *attributes: str) -> bool:
        """True if any (or any of the named) column attributes have unsaved changes."""
        state = sqla_inspect(self)
        if state is None:
            return False
        keys = list(attributes) if attributes else self._arvel_column_keys()
        return any(state.attrs[k].history.has_changes() for k in keys if k in state.attrs)

    def is_clean(self, *attributes: str) -> bool:
        return not self.is_dirty(*attributes)

    def get_dirty(self) -> dict[str, Any]:
        """Column attributes changed since load/last save, mapped to their new values."""
        state = sqla_inspect(self)
        if state is None:
            return {}
        return {
            k: getattr(self, k)
            for k in self._arvel_column_keys()
            if k in state.attrs and state.attrs[k].history.has_changes()
        }

    def get_original(self, key: str | None = None, default: Any = None) -> Any:
        """Value(s) as loaded from the DB (or last save), ignoring unsaved changes."""
        state = sqla_inspect(self)
        if state is None:
            return default if key is not None else {}
        if key is not None:
            if key in state.committed_state:
                return state.committed_state[key]
            return getattr(self, key, default)
        original: dict[str, Any] = {}
        for k in self._arvel_column_keys():
            original[k] = state.committed_state.get(k, getattr(self, k))
        return original

    def was_changed(self, *attributes: str) -> bool:
        """True if the last save modified any (or any of the named) attributes."""
        changed: frozenset[str] = self._arvel_changed or frozenset()
        if not attributes:
            return bool(changed)
        return any(a in changed for a in attributes)

    def get_changes(self) -> dict[str, Any]:
        """Attributes modified by the last save, mapped to their current values."""
        changed: frozenset[str] = self._arvel_changed or frozenset()
        return {k: getattr(self, k) for k in changed if hasattr(self, k)}

    def sync_original(self) -> Any:
        """Reset the original snapshot to the current attribute values."""
        from sqlalchemy.orm.attributes import set_committed_value

        for key in self._arvel_column_keys():
            set_committed_value(self, key, getattr(self, key))
        return self

    def _arvel_snapshot_changes(self) -> None:
        object.__setattr__(self, "_arvel_changed", frozenset(self.get_dirty().keys()))

    async def save(self) -> Any:
        from arvel.database.events import fire_after_commit, fire_async, fire_cancellable

        await fire_async(type(self), "saving", self)
        session = get_active_session()
        # Snapshot before add() moves a transient instance to pending state.
        _state = sqla_inspect(self)
        is_new = _state is None or _state.transient or not _state.has_identity
        before_event = "creating" if is_new else "updating"
        await fire_cancellable(type(self), before_event, self)
        session.add(self)
        self._arvel_snapshot_changes()
        await session.flush()
        after_event = "created" if is_new else "updated"
        await fire_async(type(self), after_event, self)
        await fire_async(type(self), "saved", self)
        fire_after_commit(type(self), self)
        return self

    async def delete(self) -> Any:
        from arvel.database.events import fire_after_commit, fire_async, fire_cancellable

        soft_field = getattr(type(self), "__arvel_soft_delete_column__", None)
        session = get_active_session()
        await fire_cancellable(type(self), "deleting", self)
        if soft_field:
            setattr(self, soft_field, _datetime.now(UTC))
            session.add(self)
            await session.flush()
            await fire_async(type(self), "deleted", self)
            fire_after_commit(type(self), self)
            return self
        await session.delete(self)
        await session.flush()
        await fire_async(type(self), "deleted", self)
        fire_after_commit(type(self), self)
        return self

    async def force_delete(self) -> Any:
        from arvel.database.events import fire_after_commit, fire_async, fire_cancellable

        session = get_active_session()
        await fire_cancellable(type(self), "deleting", self)
        await session.delete(self)
        await session.flush()
        await fire_async(type(self), "deleted", self)
        fire_after_commit(type(self), self)
        return self

    async def restore(self) -> Any:
        from arvel.database.events import fire_after_commit, fire_async, fire_cancellable

        soft_field = getattr(type(self), "__arvel_soft_delete_column__", None)
        if soft_field is None:
            raise AttributeError(f"{type(self).__name__} does not use SoftDeletes.")
        await fire_cancellable(type(self), "restoring", self)
        setattr(self, soft_field, None)
        session = get_active_session()
        session.add(self)
        await session.flush()
        await fire_async(type(self), "restored", self)
        fire_after_commit(type(self), self)
        return self

    async def fresh(self) -> Any:
        # Route through the query builder so global scopes (soft-delete etc.) apply.
        mapper = sqla_inspect(type(self))
        if mapper is None:
            raise RuntimeError(f"{type(self).__name__} is not a mapped SQLA class.")
        pk_cols = mapper.primary_key
        pk_values = tuple(getattr(self, col.key) for col in pk_cols)
        qb = type(self).query()
        for col, val in zip(pk_cols, pk_values, strict=True):
            qb = qb.where(getattr(type(self), col.key) == val)
        return await qb.first()

    async def refresh(self, *attrs: str) -> Any:
        session = get_active_session()
        await session.refresh(self, attrs or None)
        return self

    async def touch(self) -> Any:
        """Update updated_at to now and persist."""
        if hasattr(self, "updated_at"):
            object.__setattr__(self, "updated_at", _datetime.now(UTC))
        session = get_active_session()
        session.add(self)
        await session.flush()
        return self

    async def replicate(self, *, except_: list[str] | None = None) -> Any:
        """Return an unsaved copy of this model, excluding ``except_`` fields."""
        mapper = sqla_inspect(type(self))
        if mapper is None:
            raise RuntimeError(f"{type(self).__name__} is not a mapped SQLA class.")
        import inspect

        skip = set(except_ or [])
        # Eloquent drops the PK and timestamps on a fresh copy; don't carry over a
        # soft-delete flag either, or the clone would start life already trashed.
        skip.update({"created_at", "updated_at"})
        soft_field = getattr(type(self), "__arvel_soft_delete_column__", None)
        if soft_field:
            skip.add(soft_field)
        pk_cols = {col.key for col in mapper.primary_key}
        # Determine which fields are required by __init__ (no default, init=True).
        init_params = inspect.signature(type(self)).parameters
        attrs: dict[str, Any] = {}
        for col_attr in mapper.column_attrs:
            key = col_attr.key
            if key in pk_cols:
                continue
            if key in skip:
                # Pass None for required excluded params so __init__ doesn't raise.
                param = init_params.get(key)
                if param is not None and param.default is inspect.Parameter.empty:
                    attrs[key] = None
                continue
            attrs[key] = getattr(self, key)
        return cast("Any", type(self))(**attrs)

    async def load(self, *relations: str) -> None:
        """Lazy-load relations onto this already-fetched instance."""
        from sqlalchemy.orm import selectinload

        session = get_active_session()
        mapper = sqla_inspect(type(self))
        if mapper is None:
            return
        # Expire the requested relations so SQLAlchemy's selectinload will
        # replace them even when expire_on_commit=False is in use.
        session.expire(self, list(relations))
        pk_cols = mapper.primary_key
        pk_values = tuple(getattr(self, col.key) for col in pk_cols)
        stmt = select(type(self))
        for col, val in zip(pk_cols, pk_values, strict=True):
            stmt = stmt.where(col == val)
        for rel in relations:
            rel_attr = getattr(type(self), rel, None)
            if rel_attr is not None:
                stmt = stmt.options(selectinload(rel_attr))
        result = await session.execute(stmt)
        fresh = result.scalars().first()
        if fresh is not None:
            for rel in relations:
                loaded = getattr(fresh, rel, None)
                if loaded is not None:
                    object.__setattr__(self, rel, loaded)

    async def load_missing(self, *relations: str) -> None:
        """Load each relation only if not already populated on this instance."""
        state = sqla_inspect(self)
        to_load = [r for r in relations if r in (state.unloaded if state else set())]
        if to_load:
            await self.load(*to_load)

    def make_hidden(self, *fields: str) -> None:
        """Add fields to per-instance hidden list (does not mutate class-level __hidden__)."""
        current = list(getattr(self, "_instance_hidden", None) or [])
        for f in fields:
            if f not in current:
                current.append(f)
        object.__setattr__(self, "_instance_hidden", current)

    def make_visible(self, *fields: str) -> None:
        """Remove fields from per-instance hidden list."""
        current = list(getattr(self, "_instance_hidden", None) or [])
        updated = [f for f in current if f not in fields]
        object.__setattr__(self, "_instance_hidden", updated)

    def to_dict(self) -> dict[str, Any]:
        mapper = sqla_inspect(type(self))
        if mapper is None:
            raise RuntimeError(f"{type(self).__name__} is not a mapped SQLA class.")
        # Build the base dict
        data = {col.key: getattr(self, col.key) for col in mapper.column_attrs}
        # Append @accessor-backed computed attributes (Eloquent's $appends).
        appends: list[str] = list(type(self).__appends__ or [])
        for name in appends:
            data[name] = getattr(self, name)
        # Apply __visible__ (allowlist)
        visible: list[str] | None = getattr(type(self), "__visible__", None)
        if visible is not None:
            data = {k: v for k, v in data.items() if k in visible}
        # Apply __hidden__ (class-level denylist)
        hidden: list[str] | None = getattr(type(self), "__hidden__", None)
        if hidden:
            data = {k: v for k, v in data.items() if k not in hidden}
        # Apply per-instance hidden
        inst_hidden: list[str] | None = getattr(self, "_instance_hidden", None)
        if inst_hidden:
            data = {k: v for k, v in data.items() if k not in inst_hidden}
        return data

    def model_serialize(self) -> dict[str, Any]:
        """Like to_dict() but auto-converts datetime → ISO 8601 and Decimal → float.

        Respects __hidden__ / __visible__ / per-instance hidden lists.
        Falls back to __dict__ when the SQLAlchemy mapper is not available.
        """
        from decimal import Decimal

        try:
            raw = self.to_dict()
        except Exception:  # noqa: BLE001 — unmapped instances (tests, mocks, partial hydration)
            raw = {
                k: v
                for k, v in self.__dict__.items()
                if not k.startswith("_sa_") and k != "_instance_hidden"
            }
            visible: list[str] | None = getattr(type(self), "__visible__", None)
            if visible is not None:
                raw = {k: v for k, v in raw.items() if k in visible}
            hidden: list[str] | None = getattr(type(self), "__hidden__", None)
            if hidden:
                raw = {k: v for k, v in raw.items() if k not in hidden}

        result: dict[str, Any] = {}
        for key, value in raw.items():
            if isinstance(value, _datetime):
                result[key] = value.isoformat()
            elif isinstance(value, Decimal):
                result[key] = float(value)
            else:
                result[key] = value
        return result

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialise this model to a JSON string.

        Honours ``__visible__`` / ``__hidden__`` / per-instance hidden lists
        (same rules as :meth:`to_dict`). Uses Pydantic's serialiser so
        ``datetime``, ``Decimal``, ``UUID``, and ``bytes`` round-trip exactly
        as they do in framework HTTP responses — no surprises between
        ``user.to_json()`` and ``JsonResponse(user)``.
        """
        from pydantic_core import to_json

        return to_json(self.to_dict(), indent=indent).decode("utf-8")

    def to_pydantic(self, schema: type[SchemaT]) -> SchemaT:
        data: dict[str, Any] = self.to_dict()
        mapper = sqla_inspect(type(self))
        if mapper is None:
            raise RuntimeError(f"{type(self).__name__} is not a mapped SQLA class.")
        rel_keys = {r.key for r in mapper.relationships}
        for field_name in schema.model_fields:
            if field_name in rel_keys:
                state = sqla_inspect(self)
                if state is None:
                    raise RuntimeError(f"{type(self).__name__} has no SQLA state.")
                if field_name in state.unloaded:
                    raise RelationNotLoadedError(type(self).__name__, field_name)
                data[field_name] = getattr(self, field_name)
        return schema.model_validate(data)


class Model(
    MappedAsDataclass, DeclarativeBase, ActiveRecord, metaclass=_ModelMeta, init=True, kw_only=True
):
    """Base class for every Arvel model.

    Combines SQLAlchemy ``DeclarativeBase`` with ``MappedAsDataclass``
    (``kw_only=True``) so every concrete subclass gets a typed, keyword-only
    ``__init__`` derived from its ``Mapped[T]`` column annotations. The
    :class:`ActiveRecord` mixin provides the Eloquent-style class and instance
    API. The :class:`_ModelMeta` metaclass forwards unknown class-level
    attribute lookups to ``cls.query()``.

    Rules for model authors:
    - Annotate every column: ``name: Mapped[str] = string(100)``
    - Server-managed fields (auto-increment PKs, timestamps, soft-delete
      tombstones) must carry ``init=False`` so they don't appear in ``__init__``.
      The :func:`~arvel.database.columns.id_` helper already does this.
    - Mixins :class:`Timestamps` and :class:`SoftDeletes` mark their columns
      ``init=False`` for the same reason.
    """

    __abstract__ = True

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        # Validate __casts__ entries at class-definition time.
        casts: dict[str, str] | None = getattr(cls, "__casts__", None)
        if casts:
            for field_name, cast_type in casts.items():
                if cast_type not in _VALID_CASTS:
                    raise ValueError(
                        f"{cls.__name__}.__casts__['{field_name}'] = '{cast_type}' is not a "
                        f"recognised cast type. Valid: {sorted(_VALID_CASTS)}"
                    )

        # Collect @mutator-decorated methods. Walk base -> derived so a subclass
        # mutator overrides an inherited one for the same column.
        mutators: dict[str, Callable[[Any, Any], Any]] = {}
        for base in reversed(cls.__mro__):
            for attr in vars(base).values():
                if getattr(attr, "__arvel_mutator__", False):
                    column: str = attr.__arvel_mutator_column__
                    mutators[column] = attr
        if mutators:
            cls.__arvel_mutators__ = mutators

    @classmethod
    def add_global_scope(
        cls,
        name: str,
        scope: Any,
    ) -> None:
        """Register a global scope applied to every query on this model.

        ``scope`` is either a :class:`~arvel.database.scope.GlobalScope`
        instance or a callable ``(QueryBuilder) -> QueryBuilder``. The scope
        is stored on the model's own ``__arvel_global_scopes__`` dict —
        siblings and parents are not mutated.
        """
        from arvel.database.scope import GlobalScope

        if isinstance(scope, GlobalScope):
            fn: Any = scope.apply
        elif callable(scope):
            fn = scope
        else:
            raise TypeError(
                f"add_global_scope expects a callable or GlobalScope instance, "
                f"got {type(scope).__name__}"
            )

        # Don't mutate a parent's dict — clone if we're still inheriting.
        if "__arvel_global_scopes__" not in cls.__dict__:
            cls.__arvel_global_scopes__ = dict(getattr(cls, "__arvel_global_scopes__", {}))
        cls.__arvel_global_scopes__[name] = fn

    def __getattribute__(self, name: str) -> Any:
        """Apply __casts__ when reading column values."""
        value = super().__getattribute__(name)
        casts: dict[str, str] | None = type(self).__dict__.get("__casts__") or getattr(
            type(self), "__casts__", None
        )
        if not casts or name not in casts or value is None:
            return value
        caster = _CAST_DISPATCH.get(casts[name])
        return caster(value) if caster is not None else value

    def __setattr__(self, name: str, value: Any) -> None:
        # Symmetric with __getattribute__: coerce on write so SA persists the cast
        # value, and so Model(field=raw) and m.field = raw both behave the same.
        if value is not None:
            # Mutators run first (transform), then casts (storage coercion).
            mutator_fn = type(self).__arvel_mutators__.get(name)
            if mutator_fn is not None:
                value = mutator_fn(self, value)

            casts: dict[str, str] | None = type(self).__dict__.get("__casts__") or getattr(
                type(self), "__casts__", None
            )
            if casts and name in casts:
                cast_type = casts[name]
                if cast_type not in _WRITE_SKIP_CASTS:
                    caster = _CAST_DISPATCH.get(cast_type)
                    if caster is not None:
                        value = caster(value)
        super().__setattr__(name, value)

    def has_many(
        self,
        related: type[RelatedT],
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
    ) -> HasMany[RelatedT]:
        from arvel.database.orm.relations import HasMany

        lk = local_key or _pk_name(type(self))
        fk = foreign_key or f"{Str.snake(type(self).__name__)}_{lk}"
        owner_pk = getattr(self, lk)
        col = getattr(related, fk)
        qb: HasMany[RelatedT] = HasMany(related, owner=self, fk_col=fk, owner_pk=owner_pk)
        return qb.where(col == owner_pk)

    def has_one(
        self,
        related: type[RelatedT],
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
    ) -> HasOne[RelatedT]:
        from arvel.database.orm.relations import HasOne

        lk = local_key or _pk_name(type(self))
        fk = foreign_key or f"{Str.snake(type(self).__name__)}_{lk}"
        owner_pk = getattr(self, lk)
        col = getattr(related, fk)
        qb: HasOne[RelatedT] = HasOne(related, owner=self, fk_col=fk, owner_pk=owner_pk)
        return qb.where(col == owner_pk)

    def belongs_to(
        self,
        related: type[RelatedT],
        *,
        foreign_key: str | None = None,
        owner_key: str | None = None,
    ) -> BelongsTo[RelatedT]:
        from arvel.database.orm.relations import BelongsTo

        ok = owner_key or _pk_name(related)
        fk = foreign_key or f"{Str.snake(related.__name__)}_{ok}"
        fk_value = getattr(self, fk, None)
        pk_col = getattr(related, ok)
        qb: BelongsTo[RelatedT] = BelongsTo(related, owner=self, fk_attr=fk, owner_key=ok)
        if fk_value is not None:
            qb = qb.where(pk_col == fk_value)
        return qb

    @classmethod
    def has_many_through(
        cls,
        related: type[RelatedT],
        through: type[Any],
        *,
        first_key: str | None = None,
        second_key: str | None = None,
        local_key: str = "id",
    ) -> HasManyThrough[RelatedT]:
        """Return a QueryBuilder for a has-many-through relationship."""
        from arvel.database.orm.relations import HasManyThrough, ThroughSpec

        fk1 = first_key or f"{Str.snake(cls.__name__)}_id"
        fk2 = second_key or f"{Str.snake(through.__name__)}_id"
        spec = ThroughSpec(owner_cls=cls, through=through, fk1=fk1, fk2=fk2, local_key=local_key)
        return HasManyThrough(related, spec=spec)

    @classmethod
    def has_one_through(
        cls,
        related: type[RelatedT],
        through: type[Any],
        *,
        first_key: str | None = None,
        second_key: str | None = None,
        local_key: str = "id",
    ) -> HasOneThrough[RelatedT]:
        from arvel.database.orm.relations import HasOneThrough, ThroughSpec

        fk1 = first_key or f"{Str.snake(cls.__name__)}_id"
        fk2 = second_key or f"{Str.snake(through.__name__)}_id"
        spec = ThroughSpec(owner_cls=cls, through=through, fk1=fk1, fk2=fk2, local_key=local_key)
        return HasOneThrough(related, spec=spec)

    @classmethod
    def observe(cls, observer: type[Any] | Any) -> None:
        """Register an observer class or instance for lifecycle events."""
        from arvel.database.events import bind_observer

        bind_observer(cls, observer)


def _set_timestamps_on_insert(_mapper: Mapper[Any], _conn: Any, target: Any) -> None:
    now = _datetime.now(UTC)
    if getattr(target, "created_at", None) is None:
        target.created_at = now
    if getattr(target, "updated_at", None) is None:
        target.updated_at = now


def _set_timestamps_on_update(_mapper: Mapper[Any], _conn: Any, target: Any) -> None:
    target.updated_at = _datetime.now(UTC)


class Timestamps(MappedAsDataclass):
    """Mixin adding ``created_at`` and ``updated_at`` (auto-populated on save).

    Extends ``MappedAsDataclass`` so SQLAlchemy recognises it as a typed-
    dataclass mixin — required by SQLA 2.0 and will be enforced in 2.1.
    Both columns are ``init=False``; the mapper-event hook populates them.
    """

    created_at: Mapped[_datetime] = datetime(nullable=False, init=False, default=None)
    updated_at: Mapped[_datetime] = datetime(nullable=False, init=False, default=None)

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        event.listen(cls, "before_insert", _set_timestamps_on_insert, propagate=True)
        event.listen(cls, "before_update", _set_timestamps_on_update, propagate=True)


class SoftDeletes(MappedAsDataclass):
    """Mixin adding ``deleted_at`` and turning ``delete()`` into a soft delete.

    Extends ``MappedAsDataclass`` so SQLAlchemy recognises it as a typed-
    dataclass mixin. Registers a GlobalScope that excludes soft-deleted rows
    from every query. Use ``.with_trashed()`` or ``.only_trashed()`` on a
    QueryBuilder to override.
    """

    deleted_at: Mapped[_datetime | None] = datetime(nullable=True, init=False, default=None)

    __arvel_soft_delete_column__: ClassVar[str] = "deleted_at"
    __arvel_global_scopes__: ClassVar[dict[str, Any]] = {}

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        from arvel.database.scope import SoftDeleteScope

        col_name: str = getattr(cls, "__arvel_soft_delete_column__", "deleted_at")

        if "__arvel_global_scopes__" not in cls.__dict__:
            cls.__arvel_global_scopes__ = dict(getattr(cls, "__arvel_global_scopes__", {}))
        cls.__arvel_global_scopes__["soft_delete"] = SoftDeleteScope(col_name).apply


# Type aliases used in Model class body (declared after both classes to avoid forward ref)
from arvel.database.orm.relations import HasManyThrough, HasOneThrough  # noqa: E402


class Prunable:
    """Mixin that marks a model as prunable via the ``model:prune`` command.

    Implement ``prunable_query()`` to return a ``QueryBuilder`` selecting the
    rows that should be deleted. The ``model:prune`` command calls
    ``prunable_query().force_delete()`` for every registered prunable model, so
    rows are permanently removed even when the model uses SoftDeletes.

    Example — delete records older than 30 days::

        class LogEntry(Model, Timestamps, Prunable):
            __tablename__ = "log_entries"

            def prunable_query(self) -> QueryBuilder:
                cutoff = _datetime.now(UTC) - timedelta(days=30)
                return type(self).query().where(
                    type(self).created_at < cutoff
                )
    """

    def prunable_query(self) -> Any:
        """Return a ``QueryBuilder`` for the rows to prune.

        Subclasses MUST override this. The default raises ``NotImplementedError``
        so forgetting the override is immediately visible.
        """
        raise NotImplementedError(f"{type(self).__name__}.prunable_query() must be implemented.")


class ViewModel(Model):
    """Read-only base class for models backed by a database view.

    Map ``__tablename__`` to an existing view name and define columns that match
    the view's shape — all SELECT paths work identically to a regular Model.

    For materialized views set ``__is_materialized_view__ = True`` to unlock
    ``refresh()``, which emits ``REFRESH MATERIALIZED VIEW`` via the active
    database connection.

    All write operations (``create``, ``save``, ``delete``, ``insert``,
    ``update``, etc.) raise ``ReadOnlyModelError`` before touching the DB.
    """

    __abstract__ = True
    __read_only__: ClassVar[bool] = True
    __is_materialized_view__: ClassVar[bool] = False

    @classmethod
    async def create(cls, **_attrs: Any) -> Any:
        raise ReadOnlyModelError(cls.__name__, "create")

    async def save(self) -> Any:
        raise ReadOnlyModelError(type(self).__name__, "save")

    async def delete(self) -> Any:
        raise ReadOnlyModelError(type(self).__name__, "delete")

    async def force_delete(self) -> Any:
        raise ReadOnlyModelError(type(self).__name__, "force_delete")

    @classmethod
    async def refresh_view(cls, *, concurrently: bool = False) -> None:
        """Emit ``REFRESH MATERIALIZED VIEW`` for this view.

        Only valid when ``__is_materialized_view__ = True``.  Delegates to
        ``Schema.refresh_materialized_view`` using the active DB connection.
        Raises ``ReadOnlyModelError`` for regular (non-materialized) views.
        """
        if not cls.__is_materialized_view__:
            raise ReadOnlyModelError(
                cls.__name__,
                "refresh_view (only materialized views support this — "
                "set __is_materialized_view__ = True)",
            )
        from arvel.database.schema import Schema

        Schema.refresh_materialized_view(cls.__tablename__, concurrently=concurrently)


__all__ = ["ActiveRecord", "Model", "Prunable", "SoftDeletes", "Timestamps", "ViewModel"]
