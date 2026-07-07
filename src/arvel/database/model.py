"""arvel.database.model — Active-Record ``Model`` over SQLAlchemy Core.

The model *is* its DAO (``await User.where(active=True).get()``, ``await user.save()``).
The metaclass builds a Core ``Table`` cheaply at class-creation (no DB connection or
reflection at import). ``Model`` is a thin composition of focused mixins — persistence/CRUD
+ attribute access stay here; events (``model_events.HasEvents``), casts
(``model_casts.HasCasts``), relations (``model_relations.HasRelationships``), and serialization
(``model_serialization.SerializesModels``) each live in their own module. Model lifecycle events
are dispatched through the ``EventDispatcher`` **contract resolved from the container** — this
module never imports ``arvel.events`` (G1 boundary). Grounded in knowledge/port/07.
"""
# Active-Record attribute access is dynamic by nature; mypy-strict still checks it.

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from arvel.database.builder import Builder
from arvel.database.model_casts import HasCasts, now_utc, uses_text_column
from arvel.database.model_events import HasEvents
from arvel.database.model_relations import HasRelationships
from arvel.database.model_serialization import SerializesModels

if TYPE_CHECKING:
    from collections.abc import Mapping

    from arvel.database.collection import ModelCollection
    from arvel.database.connections import ConnectionResolver
    from arvel.database.factory import Factory

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


#: Concrete models keyed by their qualified name (``module.Class``) — bare class
#: names collide across modules, which silently corrupts polymorphic resolution.
_MODEL_REGISTRY: dict[str, type] = {}
#: Explicit morph aliases (``morph_map``): alias → class, plus the reverse.
_MORPH_ALIASES: dict[str, type[Any]] = {}
_ALIAS_BY_CLASS: dict[type[Any], str] = {}


def _qualified_name(model: Any) -> str:
    return f"{model.__module__}.{model.__name__}"


def morph_map(mapping: dict[str, type[Any]]) -> None:
    """Register stable morph aliases: ``{'post': Post}`` stores ``'post'`` in ``{name}_type``
    columns instead of the qualified class path, so a class rename/move can't orphan rows."""
    for alias, model in mapping.items():
        _MORPH_ALIASES[alias] = model
        _ALIAS_BY_CLASS[model] = alias


def morph_type_of(model: Any) -> str:
    """The value written to ``{name}_type`` columns: the registered alias, else the
    qualified class path."""
    return _ALIAS_BY_CLASS.get(model, _qualified_name(model))


def resolve_model(name: str) -> type | None:
    """Resolve a stored morph type (for polymorphic ``morph_to``): an explicit alias first,
    then the qualified-name registry. Unknown names resolve to ``None`` — the reading side
    treats them as a missing owner rather than crashing."""
    return _MORPH_ALIASES.get(name) or _MODEL_REGISTRY.get(name)


def scope[F: "Any"](method: F) -> F:
    """Mark a model method as a **local query scope** so it's callable on a query without the
    ``scope_`` prefix — the decorator counterpart to the ``scope_<name>`` convention ('s
    ``#[Scope]`` attribute). ``@scope def published(self, query):...`` lets you write
    ``Post.published()``. The method takes the query builder and constrains it in place."""
    method._arvel_scope = True  # marker read by Builder.__getattr__
    return method


class ModelNotFound(Exception):
    """Raised by ``find_or_fail`` / ``first_or_fail`` when no row matches.

    Carries ``status = 404`` so the HTTP kernel renders it as a 404, letting a handler use ``await Post.find_or_fail(id)`` without
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
    discarded into an empty row. parity: "Add [...] to fillable property to allow mass
    assignment". Declare ``__fillable__`` (or set ``__guarded__ = []``) to allow it."""

    def __init__(self, model: str, keys: list[str]) -> None:
        self.model = model
        self.keys = keys
        super().__init__(
            f"Add [{', '.join(keys)}] to the __fillable__ property to allow mass assignment on [{model}]."
        )


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
        elif uses_text_column(cast):
            # plain TEXT, not a native JSON/DECIMAL column: the cast already owns (de)serialization,
            # and a native column's asymmetric read/write processors would double-encode on every write
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
            _MODEL_REGISTRY[_qualified_name(cls)] = cls  # for polymorphic morph_to resolution
        return cls

    def __getattr__(cls, item: str) -> Any:
        # proxies class-level calls to a fresh query, e.g. User.where(...) -> User.query().where(...)
        return getattr(cls.query(), item)


class Model(HasEvents, HasCasts, HasRelationships, SerializesModels, metaclass=ModelMeta):
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
    __factory__: ClassVar[type[Factory[Any]] | None] = None  # override for Model.factory()
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
    def set_connection(cls, resolver: ConnectionResolver | None) -> None:
        """Bind (or with ``None`` unbind) the resolver this model class queries through —
        tests unbind in teardown so a disposed connection can't leak into later tests."""
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
        builder = Builder(cls.__table__, cls._resolve(), hydrate=cls._hydrate_and_fire, model=cls)
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
        return Builder(cls.__table__, cls._resolve(), hydrate=cls._hydrate_and_fire)

    @classmethod
    def only_trashed(cls) -> Builder:
        """Query only the soft-deleted rows."""
        return Builder(cls.__table__, cls._resolve(), hydrate=cls._hydrate_and_fire).where_not_null(
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
        """The column a route param resolves against.

        Defaults to the primary key; override to bind by a different column, e.g.::

            class Post(Model):
                @classmethod
                def get_route_key_name(cls) -> str:
                    return "slug"
        """
        return cls.__primary_key__

    @classmethod
    async def resolve_route_binding(cls, value: Any, field: str | None = None) -> Self | None:
        """Resolve a route param to a model.

        Used by the framework for **implicit** binding: a controller action typed
        ``async def show(self, post: Post)`` resolves ``{post}`` via this method
        (against:meth:`get_route_key_name`, or ``field`` for a custom key like
        ``{post:slug}``). Returns ``None`` on no match — the HTTP layer turns that
        into a 404.
        """
        column = field or cls.get_route_key_name()
        found: Self | None = await cls.where(column, "=", value).first()
        return found

    @classmethod
    async def all(cls) -> ModelCollection[Self]:
        rows: ModelCollection[Self] = await cls.get()
        return rows

    @classmethod
    async def create(cls, **attributes: Any) -> Self:
        instance = cls()
        instance.fill(attributes)
        await instance.save()
        return instance

    @classmethod
    def factory(cls) -> Factory[Self]:
        """This model's factory: ``__factory__`` if set, else the
        ``<Model>Factory`` registered for this class (registered automatically when that ``Factory``
        subclass is defined — make sure it's imported, e.g. from a seeder or test)."""
        if cls.__factory__ is not None:
            return cast("Factory[Self]", cls.__factory__())
        from arvel.database.factory import factory_for

        return cast("Factory[Self]", factory_for(cls))

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

    @classmethod
    async def _hydrate_and_fire(cls, row: dict[str, Any]) -> Self:
        """``_hydrate`` + the ``retrieved`` event — the path every DB read goes through
        (``Builder.get``/``first``/``cursor``, relation eager-loading). ``_hydrate`` itself stays
        synchronous (a stable, direct-call surface — e.g. hydrating a legacy row in a test)."""
        instance = cls._hydrate(row)
        await instance._fire("retrieved")
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
        """``totallyGuarded()`` — no fillable allow-list and everything guarded, so *nothing*
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

    # --- attribute access ----------------------------------------------------
    def __getattr__(self, item: str) -> Any:
        attributes = self.__dict__.get("_attributes", {})
        if item in attributes:
            return self._cast_get(item, attributes[item])
        if item in type(self).__attributes_meta__:  # computed accessor (no stored value)
            return self._cast_get(item, None)
        # a declared column that isn't set on this instance reads as None; an
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
        """A new *unsaved* copy: attributes minus the primary key, timestamps, and ``exclude``.

        Fires ``replicating`` on ``self`` before returning. ``replicate()``
        keeps its public **sync** signature, so the (async) event dispatch is best-effort —
        see:meth:`HasEvents._fire_sync`."""
        skip = {self.__primary_key__, "created_at", "updated_at", *exclude}
        data = {k: v for k, v in self._attributes.items() if k not in skip}
        clone = type(self)()
        object.__setattr__(clone, "_attributes", data)
        object.__setattr__(clone, "_original", {})
        object.__setattr__(clone, "_exists", False)
        self._fire_sync("replicating")
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
        now = now_utc()
        if not self._exists:
            self._attributes.setdefault("created_at", now)
        self._attributes["updated_at"] = now

    def _guard_writable(self) -> None:
        if type(self).__view__ is not None:
            raise ReadOnlyModelError(
                f"{type(self).__name__} is a read-only view ('{type(self).__view__}') — writes are not allowed."
            )

    async def save(self) -> bool:
        """Insert (new) or update (existing + dirty) this model. Lifecycle: ``saving`` →
        (``creating`` | ``updating``, only when there's actually a row to write) → the SQL → the
        matching (``created`` | ``updated``) → ``saved``. ``saving``/``creating``/``updating``
        are cancelable — an observer returning ``False`` aborts and ``save()`` returns ``False``
        (the row is left exactly as it was on disk). ``saved`` always fires, matching the prior
        (pre-lifecycle-expansion) behavior, even on a no-op save of a clean existing model."""
        self._guard_writable()
        if await self._fire("saving") is False:
            return False
        is_new = not self._exists
        self._touch_timestamps()
        resolver = self._resolve()
        performed = False
        if is_new:
            if await self._fire("creating") is False:
                return False
            if self._uses_unique_ids() and self.__primary_key__ not in self._attributes:
                self._attributes[self.__primary_key__] = self._new_unique_id()
            result = await Builder(self.__table__, resolver).insert(dict(self._attributes))
            if result.primary_key is not None and self.__primary_key__ not in self._attributes:
                self._attributes[self.__primary_key__] = result.primary_key
            object.__setattr__(self, "_exists", True)
            performed = True
        elif self.is_dirty():
            if await self._fire("updating") is False:
                return False
            await (
                Builder(self.__table__, resolver)
                .where(self.__primary_key__, "=", self._attributes[self.__primary_key__])
                .update(dict(self._attributes))
            )
            performed = True
        object.__setattr__(self, "_original", dict(self._attributes))
        if performed:
            await self._fire("created" if is_new else "updated")
        await self._fire("saved")
        await self._touch_owners()
        return True

    async def _touch_owners(self) -> None:
        """Bump ``updated_at`` on the parents named in ``__touches__``."""
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
        """Soft-delete (stamps ``deleted_at``, keeps the row — a ``SoftDeletes`` model) or
        delegates entirely to:meth:`force_delete`. ``deleting`` is cancelable — an observer
        returning ``False`` aborts and the row is left untouched."""
        self._guard_writable()
        if await self._fire("deleting") is False:
            return False
        if self._uses_soft_deletes():  # soft: stamp deleted_at, keep the row
            self._attributes["deleted_at"] = now_utc()
            await self._key_query().update({"deleted_at": self._attributes["deleted_at"]})
            await self._fire("deleted")
            await self._fire("trashed")
            return True
        return await self.force_delete()

    async def force_delete(self) -> bool:
        """Hard-delete the row, bypassing soft deletes. ``force_deleting`` is cancelable."""
        self._guard_writable()
        if await self._fire("force_deleting") is False:
            return False
        await self._key_query().delete()
        object.__setattr__(self, "_exists", False)
        await self._fire("force_deleted")
        await self._fire("deleted")
        return True

    async def restore(self) -> bool:
        """Un-soft-delete: clears ``deleted_at``. ``restoring`` is cancelable — an observer
        returning ``False`` aborts and the row stays trashed."""
        self._guard_writable()
        if await self._fire("restoring") is False:
            return False
        self._attributes["deleted_at"] = None
        await self._key_query().update({"deleted_at": None})
        await self._fire("restored")
        return True

    def trashed(self) -> bool:
        return self._attributes.get("deleted_at") is not None

    async def increment(self, column: str, amount: int = 1) -> Self:
        # atomic SET col = col + amount so concurrent increments compose instead of racing a
        # read-modify-write; still fires the update lifecycle so observers (audit/cache-bust/
        # reindex) run and an `updating` observer can cancel.
        self._guard_writable()
        if await self._fire("updating") is False:
            return self
        import sqlalchemy as sa

        # COALESCE so a NULL column increments from 0 rather than staying NULL (NULL + n = NULL)
        col = self.__table__.c[column]
        updates: dict[str, Any] = {column: sa.func.coalesce(col, 0) + amount}
        self._attributes[column] = (self._attributes.get(column) or 0) + amount
        if self.__timestamps__ and "updated_at" in self.__table__.c:
            now = now_utc()
            updates["updated_at"] = now
            self._attributes["updated_at"] = now
        await self._key_query().update(updates)
        object.__setattr__(self, "_original", dict(self._attributes))
        await self._fire("updated")
        await self._fire("saved")
        return self

    async def decrement(self, column: str, amount: int = 1) -> Self:
        return await self.increment(column, -amount)

    async def touch(self) -> Self:
        """Update the ``updated_at`` timestamp to now and persist it."""
        self._guard_writable()  # a view-backed model has no writable updated_at (D5)
        now = now_utc()
        self._attributes["updated_at"] = now
        if self._exists:
            await self._key_query().update({"updated_at": now})
        return self
