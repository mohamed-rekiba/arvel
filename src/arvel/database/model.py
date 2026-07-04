"""arvel.database.model — Active-Record ``Model`` over SQLAlchemy Core.

The model *is* its DAO (``await User.where(active=True).get()``, ``await user.save()``).
The metaclass builds a Core ``Table`` cheaply at class-creation (no DB connection or
reflection at import). Model lifecycle events are dispatched through the
``EventDispatcher`` **contract resolved from the container** — this module never
imports ``arvel.events`` (G1 boundary). Grounded in knowledge/port/07.
"""
# Active-Record attribute access is dynamic by nature; mypy-strict still checks it.

from __future__ import annotations

import enum
import json
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from arvel.database.builder import Builder

if TYPE_CHECKING:
    from collections.abc import Mapping

    from arvel.database.connections import ConnectionResolver

# Python type -> SQLAlchemy type name; temporal types get their own real DateTime/Date in _sa_type.
_PY_TO_SA = {int: "Integer", str: "String", bool: "Boolean", float: "Float", dict: "JSON"}


def _sa_type(sa: Any, field_type: Any) -> Any:
    """Resolve a ``__fields__`` field type to a SQLAlchemy column type. A pre-built ``TypeEngine``
    passes through; ``datetime``/``date`` map to real (timezone-aware) temporal columns; everything
    else uses ``_PY_TO_SA`` (defaulting to String)."""
    import datetime as _datetime

    if isinstance(field_type, sa.types.TypeEngine):
        return field_type
    if field_type is _datetime.datetime:
        return sa.DateTime(timezone=True)
    if field_type is _datetime.date:
        return sa.Date()
    if field_type is str:
        # VARCHAR(255) default — MySQL rejects length-less VARCHAR in DDL; declare sa.Text()/String(n)
        # in __fields__ for longer columns.
        return sa.String(255)
    return getattr(sa, _PY_TO_SA.get(field_type, "String"))()


_MODEL_REGISTRY: dict[str, type] = {}


def resolve_model(name: str) -> type | None:
    """Resolve a model class by its name (for polymorphic ``morph_to``)."""
    return _MODEL_REGISTRY.get(name)


def scope[F: "Any"](method: F) -> F:
    """Mark a model method as a **local query scope** so it's callable on a query without the
    ``scope_`` prefix — the decorator counterpart to the ``scope_<name>`` convention (Laravel's
    ``#[Scope]`` attribute). ``@scope def published(self, query): ...`` lets you write
    ``Post.published()``. The method takes the query builder and constrains it in place."""
    method._arvel_scope = True  # marker read by Builder.__getattr__
    return method


class ModelNotFound(Exception):
    """Raised by ``find_or_fail`` / ``first_or_fail`` when no row matches.

    Carries ``status = 404`` so the HTTP kernel renders it as a 404 (Laravel ``findOrFail`` →
    ``ModelNotFoundException`` → 404), letting a handler use ``await Post.find_or_fail(id)`` without
    a manual ``if post is None: abort(404)`` guard. The exception renderer reads ``.status``/``.detail``."""

    status = 404

    def __init__(self, message: str = "Resource not found.") -> None:
        self.detail = message
        super().__init__(message)


class ReadOnlyModelError(Exception):
    """Raised when a write is attempted on a ``__view__``-backed (read-only) model (D5)."""


class MassAssignmentException(Exception):
    """Raised by ``fill``/``create`` when a *totally-guarded* model (the default ``__guarded__ ==
    ['*']`` with no ``__fillable__``) is mass-assigned attributes — they would otherwise be silently
    discarded into an empty row. Laravel parity: "Add [...] to fillable property to allow mass
    assignment". Declare ``__fillable__`` (or set ``__guarded__ = []``) to allow it."""

    def __init__(self, model: str, keys: list[str]) -> None:
        self.model = model
        self.keys = keys
        super().__init__(
            f"Add [{', '.join(keys)}] to the __fillable__ property to allow mass assignment on [{model}]."
        )


def _json_default(value: Any) -> Any:
    """JSON fallback for ``to_json`` — Date/Decimal/Enum and anything with isoformat."""
    if isinstance(value, enum.Enum):
        return value.value
    if hasattr(value, "to_iso"):  # arvel Date
        return value.to_iso()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class SoftDeletes:
    """Marker mixin: ``class Post(Model, SoftDeletes)`` adds a ``deleted_at`` column,
    makes ``delete()`` soft, and hides trashed rows from default queries (doc 07)."""


def _generate_ulid() -> str:
    """A 26-char Crockford-base32 ULID: 48-bit millisecond time + 80 random bits, sortable."""
    import os
    import time

    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    chars = [alphabet[(value >> (5 * i)) & 0x1F] for i in range(26)]
    return "".join(reversed(chars))


class HasUuids:
    """String primary key generated as a UUIDv7 (time-ordered) on insert."""

    def _new_unique_id(self) -> str:
        import uuid

        return str(uuid.uuid7())


class HasUlids:
    """String primary key generated as a ULID (lexicographically sortable) on insert."""

    def _new_unique_id(self) -> str:
        return _generate_ulid()


class Prunable:
    """Mixin for models with prunable rows. Override ``prunable()`` to scope which rows
    ``prune()`` removes (e.g. expired tokens). Pair with a scheduled command (doc 12)."""


def _to_db_datetime(value: Any) -> Any:
    """Normalize a Date / stdlib datetime / ISO string to a **UTC-aware** stdlib ``datetime`` for
    storage. UTC is the on-disk timezone so the round-trip is instant-faithful on every dialect:
    Postgres ``timestamptz`` keeps the instant regardless, and SQLite (which drops the offset and
    reads back a naive value) then stores a UTC wall-clock that :func:`_from_db_datetime` reads as
    UTC — so a value stored in a non-UTC zone is not silently shifted on SQLite."""
    from arvel.dates import Date

    if isinstance(value, str):
        date = Date.parse(value)
    elif isinstance(value, Date):
        date = value
    else:
        date = Date.from_py(value)  # stdlib datetime (naive ⇒ app tz, aware ⇒ instant)
    return date.raw.to_tz("UTC").to_stdlib()


def _from_db_datetime(value: Any) -> Any:
    """Interpret a value read back from a DateTime column. A **naive** datetime means SQLite (which
    dropped the offset) — it was stored as a UTC wall-clock (see :func:`_to_db_datetime`), so attach
    UTC. The Builder's RAW read path (``select_raw``) skips result processors entirely, so on
    SQLite the very same column arrives as its stored **string** (``'2026-07-02 21:41:10.506842'``)
    — parse it (stdlib ``fromisoformat`` accepts the space separator) and apply the same naive-
    means-UTC rule. Anything unparseable passes through for :meth:`Date.from_py` to reject."""
    import datetime as _datetime

    if isinstance(value, str):
        try:
            value = _datetime.datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, _datetime.datetime) and value.tzinfo is None:
        from zoneinfo import ZoneInfo

        return value.replace(tzinfo=ZoneInfo("UTC"))
    return value


def _now() -> Any:
    """The current instant as a UTC-aware stdlib ``datetime`` — bound into real ``DateTime``
    timestamp/soft-delete columns (the DB driver needs a datetime, not an ISO string)."""
    from arvel.dates import Date

    return _to_db_datetime(Date.now())


def _build_table(cls: type[Any]) -> Any:
    import sqlalchemy as sa

    from arvel.support import Str

    pk = cls.__primary_key__
    columns: list[Any] = []
    if pk not in cls.__fields__:
        if HasUuids in cls.__mro__:
            # as_uuid=False: the Python side stays a string, matching what HasUuids generates
            columns.append(sa.Column(pk, sa.Uuid(as_uuid=False), primary_key=True))
        elif HasUlids in cls.__mro__:
            # a ULID is a 26-char string, NOT a uuid — keep a length-bearing VARCHAR PK
            columns.append(sa.Column(pk, sa.String(255), primary_key=True))
        else:
            columns.append(sa.Column(pk, sa.Integer, primary_key=True, autoincrement=True))
    for field_name, field_type in cls.__fields__.items():
        cast = cls.__casts__.get(field_name)
        # a "datetime"-cast field gets a real DateTime column even if declared `str`, so the column
        # type and the cast never disagree on Postgres
        if cast == "datetime" and not isinstance(field_type, sa.types.TypeEngine):
            col_type: Any = sa.DateTime(timezone=True)
        elif cast == "json":
            # plain TEXT, not sa.JSON: the cast already owns (de)serialization, and a native JSON
            # column's asymmetric read/write processors would double-encode the value on every write
            col_type = sa.Text()
        else:
            col_type = _sa_type(sa, field_type)
        columns.append(sa.Column(field_name, col_type, primary_key=(field_name == pk)))
    if cls.__timestamps__:
        for ts in ("created_at", "updated_at"):
            if ts not in cls.__fields__:
                columns.append(sa.Column(ts, sa.DateTime(timezone=True), nullable=True))
    if SoftDeletes in cls.__mro__ and "deleted_at" not in cls.__fields__:
        columns.append(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    # A __view__-backed model reads from the view relation (D5).
    name = (
        getattr(cls, "__view__", None) or cls.__table_name__ or Str.plural(Str.snake(cls.__name__))
    )
    return sa.Table(name, sa.MetaData(), *columns)


class ModelMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], ns: dict[str, Any]) -> type:
        cls = cast("type[Model]", super().__new__(mcs, name, bases, ns))
        # Attribute accessor/mutator methods are stripped from the class so `instance.<name>`
        # resolves to the attribute value (via __getattr__), not the shadowing method.
        from arvel.database.attribute import returns_attribute

        meta: dict[str, Any] = {}
        scopes: dict[str, Any] = {}
        for base in bases:
            meta.update(getattr(base, "__attributes_meta__", {}))
            scopes.update(getattr(base, "__local_scopes__", {}))
        for attr_name, member in list(ns.items()):
            if callable(member) and returns_attribute(member):
                meta[attr_name] = member
                if attr_name in cls.__dict__:
                    delattr(cls, attr_name)
            elif callable(member) and getattr(member, "_arvel_scope", False):
                # stripped so `Model.<name>` forwards to the builder instead of the shadowing method
                scopes[attr_name] = member
                if attr_name in cls.__dict__:
                    delattr(cls, attr_name)
        cls.__attributes_meta__ = meta
        cls.__local_scopes__ = scopes
        if bases and getattr(cls, "__fields__", None):  # concrete model → build its table
            cls.__table__ = _build_table(cls)
            _MODEL_REGISTRY[name] = cls  # for polymorphic morph_to resolution
        return cls

    def __getattr__(cls, item: str) -> Any:
        # proxies class-level calls to a fresh query, e.g. User.where(...) -> User.query().where(...)
        return getattr(cls.query(), item)


class Model(metaclass=ModelMeta):
    __table_name__: ClassVar[str | None] = None
    __view__: ClassVar[str | None] = None  # set → read-only model over a DB view (D5)
    __primary_key__: ClassVar[str] = "id"
    __fields__: ClassVar[dict[str, Any]] = {}
    __casts__: ClassVar[dict[str, Any]] = {}
    __fillable__: ClassVar[list[str]] = []
    __guarded__: ClassVar[list[str]] = ["*"]
    __hidden__: ClassVar[list[str]] = []
    __visible__: ClassVar[list[str]] = []
    __appends__: ClassVar[list[str]] = []
    __touches__: ClassVar[list[str]] = []  # relation names whose parent updated_at to bump on save
    __global_scopes__: ClassVar[dict[str, Any]] = {}
    __timestamps__: ClassVar[bool] = True
    __attributes_meta__: ClassVar[dict[str, Any]] = {}
    __local_scopes__: ClassVar[dict[str, Any]] = {}  # @scope-decorated methods (name → fn)
    _resolver: ClassVar[ConnectionResolver | None] = None
    __table__: ClassVar[Any] = None

    def __init__(self, **attributes: Any) -> None:
        object.__setattr__(self, "_attributes", {})
        object.__setattr__(self, "_original", {})
        object.__setattr__(self, "_exists", False)
        object.__setattr__(self, "_extra_hidden", set())
        object.__setattr__(self, "_extra_visible", set())
        object.__setattr__(self, "_relations", {})
        object.__setattr__(self, "_accessor_cache", {})
        for key, val in attributes.items():
            self._attributes[key] = self._cast_set(key, val)

    # --- connection / query --------------------------------------------------
    @classmethod
    def set_connection(cls, resolver: ConnectionResolver) -> None:
        cls._resolver = resolver

    @classmethod
    def _resolve(cls) -> ConnectionResolver | None:
        if cls._resolver is not None:
            return cls._resolver
        from arvel.kernel import app, has_application

        if has_application() and app().bound("db"):
            resolver: ConnectionResolver = app().make("db")
            return resolver
        return None

    @classmethod
    def _uses_soft_deletes(cls) -> bool:
        return issubclass(cls, SoftDeletes)

    @classmethod
    def _base_query(cls, *, skip_scopes: tuple[str, ...] = ()) -> Builder:
        builder = Builder(cls.__table__, cls._resolve(), hydrate=cls._hydrate, model=cls)
        if cls._uses_soft_deletes():  # default scope: exclude trashed rows
            builder = builder.where_null("deleted_at")
        for name, scope in cls._global_scopes().items():
            if name not in skip_scopes:
                scope(builder)  # mutates the builder (adds wheres etc.)
        return builder

    @classmethod
    def query(cls) -> Builder:
        return cls._base_query()

    # Typed proxies: __getattr__ already forwards any builder method to query(), but untyped (Any),
    # which trips strict type-checking — these give the common ones a real Builder return type.
    @classmethod
    def where(cls, *args: Any, **kwargs: Any) -> Builder:
        return cls.query().where(*args, **kwargs)

    @classmethod
    def or_where(cls, *args: Any, **kwargs: Any) -> Builder:
        return cls.query().or_where(*args, **kwargs)

    @classmethod
    def where_in(cls, column: str, values: Any) -> Builder:
        return cls.query().where_in(column, values)

    @classmethod
    def where_not_in(cls, column: str, values: Any) -> Builder:
        return cls.query().where_not_in(column, values)

    @classmethod
    def with_(cls, *names: str, **constrained: Any) -> Builder:
        return cls.query().with_(*names, **constrained)

    @classmethod
    def order_by(cls, column: str, direction: str = "asc") -> Builder:
        return cls.query().order_by(column, direction)

    def recursive(
        self,
        related: Any,
        foreign_key: str,
        *,
        local_key: str | None = None,
        direction: str = "down",
        depth_key: str = "depth",
    ) -> Any:
        """A self-referential **recursive relation** over an adjacency-list tree. Define it like
        any relation::

            def descendants(self): return self.recursive(Category, "parent_id")
            def ancestors(self):   return self.recursive(Category, "parent_id", direction="up")

        ``.get()`` returns a flat list of models, each carrying a ``depth`` (1 = direct
        child/parent); ``.tree().get()`` returns a nested structure. ``direction="down"`` walks
        children, ``"up"`` walks parents. (For low-level custom recursion use
        ``Builder.recursive_cte`` / ``from_cte``.)"""
        from arvel.database.relations import RecursiveRelation

        return RecursiveRelation(
            self,
            related,
            foreign_key,
            local_key=local_key or self.__primary_key__,
            direction=direction,
            depth_key=depth_key,
        )

    @classmethod
    def _uses_unique_ids(cls) -> bool:
        return HasUuids in cls.__mro__ or HasUlids in cls.__mro__

    @classmethod
    def prunable(cls) -> Builder:
        """Override to scope which rows ``prune()`` removes (default: all)."""
        return cls.query()

    @classmethod
    async def prune(cls) -> Any:
        """Delete every row matching ``prunable()`` (Prunable mixin)."""
        return await cls.prunable().delete()

    @classmethod
    def _global_scopes(cls) -> dict[str, Any]:
        scopes: dict[str, Any] = getattr(cls, "__global_scopes__", {})
        return scopes

    @classmethod
    def add_global_scope(cls, name: str, callback: Any) -> None:
        """Register a query scope applied automatically to every query for this model."""
        own = cls.__dict__.get("__global_scopes__")
        if own is None:  # copy-on-write so subclasses don't share a parent's dict
            own = dict(getattr(cls, "__global_scopes__", {}))
            cls.__global_scopes__ = own
        own[name] = callback

    @classmethod
    def without_global_scope(cls, name: str) -> Builder:
        """A query with the named global scope skipped."""
        return cls._base_query(skip_scopes=(name,))

    @classmethod
    def without_global_scopes(cls) -> Builder:
        """A query with all global scopes skipped."""
        return cls._base_query(skip_scopes=tuple(cls._global_scopes().keys()))

    @classmethod
    def with_trashed(cls) -> Builder:
        """Query including soft-deleted rows (no default scope)."""
        return Builder(cls.__table__, cls._resolve(), hydrate=cls._hydrate)

    @classmethod
    def only_trashed(cls) -> Builder:
        """Query only the soft-deleted rows."""
        return Builder(cls.__table__, cls._resolve(), hydrate=cls._hydrate).where_not_null(
            "deleted_at"
        )

    # --- finders -------------------------------------------------------------
    @classmethod
    async def find(cls, key: Any) -> Self | None:
        found: Self | None = await cls.where(cls.__primary_key__, "=", key).first()
        return found

    @classmethod
    async def find_or_fail(cls, key: Any) -> Self:
        found = await cls.find(key)
        if found is None:
            raise ModelNotFound(f"{cls.__name__} {key!r} not found")
        return found

    # --- route-model binding -------------------------------------------------
    @classmethod
    def get_route_key_name(cls) -> str:
        """The column a route param resolves against (Laravel ``getRouteKeyName``).

        Defaults to the primary key; override to bind by a different column, e.g.::

            class Post(Model):
                @classmethod
                def get_route_key_name(cls) -> str:
                    return "slug"
        """
        return cls.__primary_key__

    @classmethod
    async def resolve_route_binding(cls, value: Any, field: str | None = None) -> Self | None:
        """Resolve a route param to a model (Laravel ``resolveRouteBinding``).

        Used by the framework for **implicit** binding: a controller action typed
        ``async def show(self, post: Post)`` resolves ``{post}`` via this method
        (against :meth:`get_route_key_name`, or ``field`` for a custom key like
        ``{post:slug}``). Returns ``None`` on no match — the HTTP layer turns that
        into a 404.
        """
        column = field or cls.get_route_key_name()
        found: Self | None = await cls.where(column, "=", value).first()
        return found

    @classmethod
    async def all(cls) -> list[Self]:
        rows: list[Self] = await cls.get()
        return rows

    @classmethod
    async def create(cls, **attributes: Any) -> Self:
        instance = cls()
        instance.fill(attributes)
        await instance.save()
        return instance

    @classmethod
    async def first_or_create(
        cls, attributes: Mapping[str, Any], values: Mapping[str, Any] | None = None
    ) -> Self:
        existing: Self | None = await cls.where(**attributes).first()
        if existing is not None:
            return existing
        return await cls.create(**{**attributes, **(values or {})})

    @classmethod
    async def update_or_create(
        cls, attributes: Mapping[str, Any], values: Mapping[str, Any] | None = None
    ) -> Self:
        existing: Self | None = await cls.where(**attributes).first()
        if existing is not None:
            existing.fill(values or {})
            await existing.save()
            return existing
        return await cls.create(**{**attributes, **(values or {})})

    @classmethod
    def _hydrate(cls, row: dict[str, Any]) -> Self:
        instance = cls()
        object.__setattr__(instance, "_attributes", dict(row))
        object.__setattr__(instance, "_original", dict(row))
        object.__setattr__(instance, "_exists", True)
        return instance

    # --- mass assignment -----------------------------------------------------
    def _is_fillable(self, key: str) -> bool:
        if key in self.__fillable__:
            return True
        if self.__fillable__:
            return False
        if "*" in self.__guarded__:
            return False
        return key not in self.__guarded__

    def _totally_guarded(self) -> bool:
        """Laravel ``totallyGuarded()`` — no fillable allow-list and everything guarded, so *nothing*
        is mass-assignable. In that state a discarded attribute is a developer error, not a silent drop."""
        return not self.__fillable__ and self.__guarded__ == ["*"]

    def fill(self, attributes: Mapping[str, Any]) -> Self:
        discarded: list[str] = []
        for key, val in attributes.items():
            if self._is_fillable(key):
                self._attributes[key] = self._cast_set(key, val)
            else:
                discarded.append(key)
        if discarded and self._totally_guarded():
            raise MassAssignmentException(type(self).__name__, discarded)
        return self

    # --- relations -----------------------------------------------------------
    def has_many(
        self, related: Any, foreign_key: str | None = None, local_key: str | None = None
    ) -> Any:
        from arvel.database.relations import HasMany
        from arvel.support import Str

        fk = foreign_key or f"{Str.snake(type(self).__name__)}_id"
        return HasMany(self, related, fk, local_key or self.__primary_key__)

    def has_one(
        self, related: Any, foreign_key: str | None = None, local_key: str | None = None
    ) -> Any:
        from arvel.database.relations import HasOne
        from arvel.support import Str

        fk = foreign_key or f"{Str.snake(type(self).__name__)}_id"
        return HasOne(self, related, fk, local_key or self.__primary_key__)

    def belongs_to(
        self, related: Any, foreign_key: str | None = None, owner_key: str | None = None
    ) -> Any:
        from arvel.database.relations import BelongsTo
        from arvel.support import Str

        fk = foreign_key or f"{Str.snake(related.__name__)}_id"
        return BelongsTo(self, related, fk, owner_key or related.__primary_key__)

    def belongs_to_many(
        self,
        related: Any,
        pivot: str | None = None,
        foreign_pivot_key: str | None = None,
        related_pivot_key: str | None = None,
    ) -> Any:
        from arvel.database.relations import BelongsToMany
        from arvel.support import Str

        me = Str.snake(type(self).__name__)
        them = Str.snake(related.__name__)
        pivot = pivot or "_".join(sorted([me, them]))
        return BelongsToMany(
            self,
            related,
            pivot,
            foreign_pivot_key or f"{me}_id",
            related_pivot_key or f"{them}_id",
            self.__primary_key__,
            related.__primary_key__,
        )

    def has_many_through(
        self,
        related: Any,
        through: Any,
        first_key: str | None = None,
        second_key: str | None = None,
    ) -> Any:
        from arvel.database.relations import HasManyThrough
        from arvel.support import Str

        return HasManyThrough(
            self,
            related,
            through,
            first_key or f"{Str.snake(type(self).__name__)}_id",
            second_key or f"{Str.snake(through.__name__)}_id",
            self.__primary_key__,
            through.__primary_key__,
        )

    def has_one_through(
        self,
        related: Any,
        through: Any,
        first_key: str | None = None,
        second_key: str | None = None,
    ) -> Any:
        from arvel.database.relations import HasOneThrough
        from arvel.support import Str

        return HasOneThrough(
            self,
            related,
            through,
            first_key or f"{Str.snake(type(self).__name__)}_id",
            second_key or f"{Str.snake(through.__name__)}_id",
            self.__primary_key__,
            through.__primary_key__,
        )

    def morph_many(self, related: Any, name: str) -> Any:
        from arvel.database.relations import MorphMany

        return MorphMany(self, related, name, self.__primary_key__)

    def morph_one(self, related: Any, name: str) -> Any:
        from arvel.database.relations import MorphOne

        return MorphOne(self, related, name, self.__primary_key__)

    def morph_to(self, name: str) -> Any:
        from arvel.database.relations import MorphTo

        return MorphTo(self, name)

    def morph_to_many(self, related: Any, name: str, pivot: str | None = None) -> Any:
        from arvel.database.relations import MorphToMany

        return MorphToMany(self, related, name, pivot)

    def morphed_by_many(self, related: Any, name: str, pivot: str | None = None) -> Any:
        from arvel.database.relations import MorphedByMany

        return MorphedByMany(self, related, name, pivot)

    def relation(self, name: str) -> Any:
        """Read an eager-loaded relation (loaded via ``Model.with_(name)``)."""
        return self._relations.get(name)

    # --- attribute access ----------------------------------------------------
    def __getattr__(self, item: str) -> Any:
        attributes = self.__dict__.get("_attributes", {})
        if item in attributes:
            return self._cast_get(item, attributes[item])
        if item in type(self).__attributes_meta__:  # computed accessor (no stored value)
            return self._cast_get(item, None)
        # a declared column that isn't set on this instance reads as None (Laravel parity); an
        # unknown attribute (typo / missing relation) still raises
        table = type(self).__table__
        if table is not None and item in table.columns:
            return self._cast_get(item, None)
        raise AttributeError(item)

    def __setattr__(self, key: str, value: Any) -> None:
        if key.startswith("_") or key in type(self).__dict__:
            object.__setattr__(self, key, value)
        else:
            self._attributes[key] = self._cast_set(key, value)

    # --- change tracking -----------------------------------------------------
    def is_dirty(self) -> bool:
        return bool(self._attributes != self._original)

    def is_clean(self) -> bool:
        return not self.is_dirty()

    def get_original(self, key: str | None = None) -> Any:
        return dict(self._original) if key is None else self._original.get(key)

    def was_changed(self, key: str | None = None) -> bool:
        if key is None:
            return self.is_dirty()
        return bool(self._attributes.get(key) != self._original.get(key))

    def get_dirty(self) -> dict[str, Any]:
        """The subset of attributes that differ from their persisted (original) value."""
        return {
            key: value
            for key, value in self._attributes.items()
            if value != self._original.get(key)
        }

    def replicate(self, *, exclude: tuple[str, ...] = ()) -> Self:
        """A new *unsaved* copy: attributes minus the primary key, timestamps, and ``exclude``."""
        skip = {self.__primary_key__, "created_at", "updated_at", *exclude}
        data = {k: v for k, v in self._attributes.items() if k not in skip}
        clone = type(self)()
        object.__setattr__(clone, "_attributes", data)
        object.__setattr__(clone, "_original", {})
        object.__setattr__(clone, "_exists", False)
        return clone

    async def fresh(self) -> Self | None:
        return await type(self).find(self._attributes[self.__primary_key__])

    async def refresh(self) -> Self:
        latest = await self.fresh()
        if latest is not None:
            object.__setattr__(self, "_attributes", dict(latest._attributes))
            object.__setattr__(self, "_original", dict(latest._attributes))
        return self

    # --- persistence ---------------------------------------------------------
    def _touch_timestamps(self) -> None:
        if not self.__timestamps__:
            return
        now = _now()
        if not self._exists:
            self._attributes.setdefault("created_at", now)
        self._attributes["updated_at"] = now

    def _guard_writable(self) -> None:
        if type(self).__view__ is not None:
            raise ReadOnlyModelError(
                f"{type(self).__name__} is a read-only view ('{type(self).__view__}') — writes are not allowed."
            )

    async def save(self) -> bool:
        self._guard_writable()
        if await self._fire("saving") is False:
            return False
        self._touch_timestamps()
        resolver = self._resolve()
        if self._exists:
            if self.is_dirty():
                await (
                    Builder(self.__table__, resolver)
                    .where(self.__primary_key__, "=", self._attributes[self.__primary_key__])
                    .update(dict(self._attributes))
                )
        else:
            if self._uses_unique_ids() and self.__primary_key__ not in self._attributes:
                self._attributes[self.__primary_key__] = self._new_unique_id()
            result = await Builder(self.__table__, resolver).insert(dict(self._attributes))
            if result.primary_key is not None and self.__primary_key__ not in self._attributes:
                self._attributes[self.__primary_key__] = result.primary_key
            object.__setattr__(self, "_exists", True)
        object.__setattr__(self, "_original", dict(self._attributes))
        await self._fire("saved")
        await self._touch_owners()
        return True

    async def _touch_owners(self) -> None:
        """Bump ``updated_at`` on the parents named in ``__touches__`` (Laravel ``$touches``)."""
        for name in self.__touches__:
            relation = getattr(self, name)()
            parent = await relation.first()
            if parent is not None:
                await parent.touch()

    def _key_query(self) -> Builder:
        return Builder(self.__table__, self._resolve()).where(
            self.__primary_key__, "=", self._attributes[self.__primary_key__]
        )

    async def delete(self) -> bool:
        self._guard_writable()
        if self._uses_soft_deletes():  # soft: stamp deleted_at, keep the row
            self._attributes["deleted_at"] = _now()
            await self._key_query().update({"deleted_at": self._attributes["deleted_at"]})
            await self._fire("deleted")
            return True
        return await self.force_delete()

    async def force_delete(self) -> bool:
        self._guard_writable()
        await self._key_query().delete()
        object.__setattr__(self, "_exists", False)
        await self._fire("deleted")
        return True

    async def restore(self) -> bool:
        self._guard_writable()
        self._attributes["deleted_at"] = None
        await self._key_query().update({"deleted_at": None})
        await self._fire("restored")
        return True

    def trashed(self) -> bool:
        return self._attributes.get("deleted_at") is not None

    async def increment(self, column: str, amount: int = 1) -> Self:
        self._attributes[column] = (self._attributes.get(column) or 0) + amount
        await self.save()
        return self

    async def decrement(self, column: str, amount: int = 1) -> Self:
        return await self.increment(column, -amount)

    async def touch(self) -> Self:
        """Update the ``updated_at`` timestamp to now and persist it."""
        self._guard_writable()  # a view-backed model has no writable updated_at (D5)
        now = _now()
        self._attributes["updated_at"] = now
        if self._exists:
            await self._key_query().update({"updated_at": now})
        return self

    # --- serialization -------------------------------------------------------
    def make_hidden(self, *keys: str) -> Self:
        self._extra_hidden.update(keys)
        self._extra_visible.difference_update(keys)
        return self

    def make_visible(self, *keys: str) -> Self:
        """Reveal attributes for this instance — including ones in the class ``__hidden__``
        list (Laravel ``makeVisible``), not only those previously hidden via ``make_hidden``."""
        self._extra_visible.update(keys)
        self._extra_hidden.difference_update(keys)
        return self

    def to_dict(self) -> dict[str, Any]:
        data = {key: self._cast_get(key, value) for key, value in self._attributes.items()}
        for key in self.__appends__:  # computed accessors not stored as attributes
            data[key] = self._cast_get(key, None)
        if self.__visible__:
            data = {k: v for k, v in data.items() if k in self.__visible__}
        hidden = (set(self.__hidden__) | self._extra_hidden) - self._extra_visible
        for key in hidden:
            data.pop(key, None)
        # Laravel toArray parity: eager-loaded relations serialize (nested) alongside attributes —
        # a has-many/many-to-many → a list of dicts, a has-one/belongs-to → a single nested dict,
        # a null relation → None. Only LOADED relations appear (unloaded ones are not serialized).
        for name, related in self._relations.items():
            data[name] = self._relation_to_dict(related)
        return data

    @staticmethod
    def _relation_to_dict(related: Any) -> Any:
        if related is None:  # a loaded but empty has-one / belongs-to (Laravel → null)
            return None
        if isinstance(related, Model):  # has-one / belongs-to → a single nested dict
            return related.to_dict()
        # a has-many / belongs-to-many result: a list/Collection of models → a list of dicts
        return [item.to_dict() for item in related]

    def to_json(self, **kwargs: Any) -> str:
        """Serialize ``to_dict()`` to a JSON string, honoring hidden/visible/appends (D3)."""
        return json.dumps(self.to_dict(), default=_json_default, **kwargs)

    # --- casts ---------------------------------------------------------------
    def _accessor(self, key: str) -> Any:
        """The Attribute for ``key`` if a model accessor/mutator method defines one."""
        method = type(self).__attributes_meta__.get(key)
        return method(self) if method is not None else None

    def _effective_cast(self, key: str) -> Any:
        """The cast for ``key`` — an explicit ``__casts__`` entry, an implicit ``datetime`` for the
        timestamp/soft-delete columns (Laravel casts created_at/updated_at/deleted_at to Carbon by
        default), or for a field *declared* with a ``datetime`` type — so a real ``DateTime`` column
        always normalizes on write (→ datetime) and reads back as ``Date``, without a redundant cast."""
        import datetime as _datetime

        cast = self.__casts__.get(key)
        if cast is not None:
            return cast
        if key in ("created_at", "updated_at") and self.__timestamps__:
            return "datetime"
        if key == "deleted_at" and self._uses_soft_deletes():
            return "datetime"
        if self.__fields__.get(key) is _datetime.datetime:
            return "datetime"
        return None

    def _cast_get(self, key: str, value: Any) -> Any:
        attr = self._accessor(key)
        if attr is not None and attr.get is not None:
            if attr.cached and key in self._accessor_cache:
                return self._accessor_cache[key]
            result = attr.get(value, self._attributes)
            if attr.cached:
                self._accessor_cache[key] = result
            return result
        cast = self._effective_cast(key)
        if value is None or cast is None:
            return value
        if not isinstance(cast, (str, type)) and hasattr(cast, "get"):  # custom Cast protocol
            return cast.get(self, key, value, self._attributes)
        if isinstance(cast, type) and issubclass(cast, enum.Enum):
            return cast(value)
        if cast == "datetime":
            from arvel.dates import Date

            return value if isinstance(value, Date) else Date.from_py(_from_db_datetime(value))
        if cast == "bool":
            return bool(value)
        if cast == "int":
            return int(value)
        if cast == "json":
            return json.loads(value) if isinstance(value, str) else value
        if cast == "encrypted":
            return self._crypt().decrypt(value)
        return value

    def _cast_set(self, key: str, value: Any) -> Any:
        attr = self._accessor(key)
        if attr is not None and attr.set is not None:
            return attr.set(value, self._attributes)
        cast = self._effective_cast(key)
        if cast is None:
            return value
        if not isinstance(cast, (str, type)) and hasattr(cast, "set"):  # custom Cast protocol
            return cast.set(self, key, value, self._attributes)
        if isinstance(value, enum.Enum):
            return value.value
        if cast == "json" and not isinstance(value, str):
            # _json_default handles Date/datetime/Decimal/Enum nested in the value (e.g. an activity
            # log snapshot of a model whose attributes include timestamps) — plain json.dumps can't.
            return json.dumps(value, default=_json_default)
        if cast == "datetime" and value is not None:
            # store a UTC-aware stdlib datetime so SQLAlchemy binds it to the real DateTime column
            # (accepts a Date, an ISO string, or a datetime) and the round-trip stays instant-faithful
            return _to_db_datetime(value)
        if cast == "hashed" and value is not None:
            return self._hash().make(value)
        if cast == "encrypted" and value is not None:
            return self._crypt().encrypt(value)
        return value

    @staticmethod
    def _crypt() -> Any:
        from arvel.kernel import app

        return app("encrypter")

    @staticmethod
    def _hash() -> Any:
        # resolve_hasher() returns the app-bound hasher when running, else a default Hasher — so a
        # `hashed` cast (e.g. User.password) works in tests/seeders without a booted app.
        from arvel.security import resolve_hasher

        return resolve_hasher()

    # --- model events via the EventDispatcher CONTRACT (no arvel.events import)
    #: lifecycle hooks an observer may handle (arvel fires these; `saving` may return False to cancel)
    OBSERVABLE_EVENTS: ClassVar[tuple[str, ...]] = ("saving", "saved", "deleted", "restored")

    @classmethod
    def observe(cls, observer: Any) -> None:
        """Register a model observer (Laravel ``Model::observe``). For each lifecycle hook the observer
        defines a method for (``saving``/``saved``/``deleted``/``restored``), wire that method to this
        model's event so it runs when the model fires it. ``saving`` returning ``False`` cancels the
        save. Call from a provider's ``boot()`` (the events dispatcher must be bound). No-op without an
        app/dispatcher."""
        from arvel.kernel import app, has_application

        if not (has_application() and app().bound("events")):
            return
        instance = observer() if isinstance(observer, type) else observer
        dispatcher = app().make("events")
        for hook in cls.OBSERVABLE_EVENTS:
            method = getattr(instance, hook, None)
            if callable(method):
                dispatcher.listen(f"{cls.__name__}.{hook}", method)

    async def _fire(self, hook: str) -> Any:
        from arvel.kernel import app, has_application

        if not has_application():
            return None
        container = app()
        if not container.bound("events"):
            return None
        dispatcher = container.make("events")
        return await dispatcher.until(f"{type(self).__name__}.{hook}", self)
