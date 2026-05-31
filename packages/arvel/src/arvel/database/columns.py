"""Typed column helpers for Arvel models — Laravel-shaped vocabulary.

These helpers mirror :class:`arvel.database.Blueprint` so the schema DSL and
the model layer speak the same language::

    # Migration (Schema DSL)
    t.id()
    t.string("name", 255)
    t.string("email", 255).unique().index()
    t.foreign_id("user_id", references="users.id")

    # Model (columns module) — plain annotation, recommended
    id:      int = id_()
    name:    str = string(255)
    email:   str = string(255, unique=True, index=True)
    user_id: int = foreign_id("users.id")

The helpers return ``Mapped[T]`` and the model metaclass wraps the plain
annotation, so ``id: int = id_()`` is all you write and the runtime value is a
SQLAlchemy ``mapped_column(...)`` the declarative scan picks up. mypy's SQLA
plugin understands this; pyright (no SQLA plugin) doesn't run the metaclass, so
under ``--strict`` it flags the assignment — annotate ``id: Mapped[int] = id_()``
to silence it. Framework mixins use the ``Mapped[T]`` form for that reason.

Why kwargs and not a fluent chain (``string(255).unique().index()``)? The
chain shape would require the model metaclass to intercept ``_ColumnBuilder``
instances before SQLAlchemy's declarative scan runs, which is fragile against
SQLA upgrades. A fluent layer over these kwargs can be added later without
breaking any existing call site.
"""

from __future__ import annotations

import enum as _enum
import uuid as _uuid
from collections.abc import Callable
from datetime import datetime as _datetime
from decimal import Decimal
from typing import Any, Final, Literal, TypeVar, cast, overload

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeEngine

_T = TypeVar("_T")


class _MutableJSONList(MutableList[Any]):
    """MutableList used for JSON columns whose root value is a list."""


class _MutableJSONDict(MutableDict[str, Any]):
    """Tracks in-place changes on JSON columns so a flush picks them up.

    SQLAlchemy's stock MutableDict rejects non-dict payloads, which would break
    JSON columns holding a list. This coerces dict roots to a tracked dict and
    list roots to a tracked list, so ``model.meta["k"] = v`` (or ``.append(x)``)
    marks the row dirty either way. Scalars stay as plain values.
    """

    @classmethod
    def coerce(cls, key: str, value: Any) -> Any:
        if isinstance(value, cls | _MutableJSONList) or value is None:
            return value
        if isinstance(value, dict):
            return cls(cast("dict[str, Any]", value))
        if isinstance(value, list):
            return _MutableJSONList(cast("list[object]", value))
        # A scalar JSON root can't carry the parent link the listener needs.
        raise TypeError(
            f"json/jsonb column {key!r} expects a dict or list value, got {type(value).__name__}."
        )


def _apply_json_default(kw: dict[str, Any], default: object) -> None:
    """Set default vs default_factory so callables (e.g. dict) don't warn under dataclasses."""
    if isinstance(default, _Unset):
        return
    if callable(default):
        kw["default_factory"] = default
    else:
        kw["default"] = default


class _Unset:
    """Sentinel: caller did not supply a default for this column.

    Column helpers use this to distinguish "no default specified" (the
    column is a required constructor argument in MappedAsDataclass) from
    "default is None" (the column is optional with a None default).
    """

    def __repr__(self) -> str:
        return "UNSET"


_UNSET: Final = _Unset()

__all__ = [
    "big_integer",
    "boolean",
    "column",
    "datetime",
    "decimal",
    "enum",
    "foreign_id",
    "foreign_string",
    "foreign_uuid",
    "id_",
    "integer",
    "json",
    "jsonb",
    "nullable_column",
    "string",
    "text",
    "uuid",
    "uuid_id",
]


def id_(
    *,
    autoincrement: bool = True,
    init: bool = False,
) -> Mapped[int]:
    """Integer primary key with auto-increment (BIGSERIAL).

    Mirrors :meth:`Blueprint.id` (default ``IdType.INT``)::

        id: Mapped[int] = id_()

    ``init=False`` by default — the database provides the value on INSERT.
    """
    return mapped_column(
        Integer, primary_key=True, autoincrement=autoincrement, init=init, default=None
    )


def uuid_id(
    *,
    init: bool = False,
) -> Mapped[_uuid.UUID]:
    """UUID v7 primary key.

    Use for entities whose ID escapes the database (URLs, emails, external APIs)::

        id: Mapped[_uuid.UUID] = uuid_id()

    For internal join tables never directly addressed by clients, prefer
    :func:`id_` (BIGSERIAL) instead.
    """
    return mapped_column(
        Uuid,
        default_factory=_uuid.uuid7,
        primary_key=True,
        init=init,
    )


@overload
def uuid(
    *,
    nullable: Literal[False] = ...,
    unique: bool = ...,
    index: bool = ...,
    as_uuid: bool = ...,
    init: bool = ...,
    default: str | _Unset = ...,
) -> Mapped[str]: ...
@overload
def uuid(
    *,
    nullable: Literal[True],
    unique: bool = ...,
    index: bool = ...,
    as_uuid: bool = ...,
    init: bool = ...,
    default: str | None | _Unset = ...,
) -> Mapped[str | None]: ...
def uuid(
    *,
    nullable: bool = False,
    unique: bool = False,
    index: bool = False,
    as_uuid: bool = True,
    init: bool = True,
    default: str | None | _Unset = _UNSET,
) -> Mapped[str | None]:
    """UUID column. Mirrors :meth:`Blueprint.uuid`.

    ``as_uuid=False`` stores/returns the value as a string rather than a Python
    ``uuid.UUID`` — needed for VARCHAR-backed UUID columns. ``init=False`` keeps
    the column out of the dataclass ``__init__`` for system-populated values.
    """
    kw: dict[str, Any] = {
        "nullable": nullable,
        "unique": unique,
        "index": index,
        "init": init,
    }
    if not isinstance(default, _Unset):
        kw["default"] = default
    sa_type = Uuid(as_uuid=True) if as_uuid else Uuid(as_uuid=False)
    return mapped_column(sa_type, **kw)


@overload
def string(
    length: int = ...,
    *,
    nullable: Literal[False] = ...,
    unique: bool = ...,
    index: bool = ...,
    init: bool = ...,
    default: str | _Unset = ...,
) -> Mapped[str]: ...
@overload
def string(
    length: int = ...,
    *,
    nullable: Literal[True],
    unique: bool = ...,
    index: bool = ...,
    init: bool = ...,
    default: str | None | _Unset = ...,
) -> Mapped[str | None]: ...
def string(
    length: int = 255,
    *,
    nullable: bool = False,
    unique: bool = False,
    index: bool = False,
    init: bool = True,
    default: str | None | _Unset = _UNSET,
) -> Mapped[str | None]:
    """``VARCHAR(length)`` column. Mirrors :meth:`Blueprint.string`.

    Without an explicit ``default``, the column is a required keyword argument
    in the ``MappedAsDataclass``-generated ``__init__``.  Pass
    ``default=None`` (or any value) to make it optional::

        name: str = string(255)                    # required in __init__
        slug: str | None = string(255, default=None)   # optional

    Pass ``init=False`` for system-populated columns that shouldn't appear in
    the dataclass ``__init__``.

    >>> name: str = string(255)
    >>> email: str = string(255, unique=True, index=True)
    """
    kw: dict[str, Any] = {"nullable": nullable, "unique": unique, "index": index, "init": init}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(String(length=length), **kw)


@overload
def text(*, nullable: Literal[False] = ..., default: str | _Unset = ...) -> Mapped[str]: ...
@overload
def text(*, nullable: Literal[True], default: str | None | _Unset = ...) -> Mapped[str | None]: ...
def text(
    *,
    nullable: bool = False,
    default: str | None | _Unset = _UNSET,
) -> Mapped[str | None]:
    """``TEXT`` column. Mirrors :meth:`Blueprint.text`."""
    kw: dict[str, Any] = {"nullable": nullable}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(Text(), **kw)


@overload
def integer(
    *,
    nullable: Literal[False] = ...,
    unique: bool = ...,
    index: bool = ...,
    init: bool = ...,
    default: int | _Unset = ...,
) -> Mapped[int]: ...
@overload
def integer(
    *,
    nullable: Literal[True],
    unique: bool = ...,
    index: bool = ...,
    init: bool = ...,
    default: int | None | _Unset = ...,
) -> Mapped[int | None]: ...
def integer(
    *,
    nullable: bool = False,
    unique: bool = False,
    index: bool = False,
    init: bool = True,
    default: int | None | _Unset = _UNSET,
) -> Mapped[int | None]:
    """``INTEGER`` column. Mirrors :meth:`Blueprint.integer`.

    Pass ``init=False`` for system-populated columns kept out of ``__init__``.
    """
    kw: dict[str, Any] = {"nullable": nullable, "unique": unique, "index": index, "init": init}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(Integer, **kw)


@overload
def big_integer(
    *,
    nullable: Literal[False] = ...,
    unique: bool = ...,
    default: int | _Unset = ...,
) -> Mapped[int]: ...
@overload
def big_integer(
    *,
    nullable: Literal[True],
    unique: bool = ...,
    default: int | None | _Unset = ...,
) -> Mapped[int | None]: ...
def big_integer(
    *,
    nullable: bool = False,
    unique: bool = False,
    default: int | None | _Unset = _UNSET,
) -> Mapped[int | None]:
    """``BIGINT`` column. Mirrors :meth:`Blueprint.big_integer`."""
    kw: dict[str, Any] = {"nullable": nullable, "unique": unique}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(BigInteger, **kw)


@overload
def boolean(*, nullable: Literal[False] = ..., default: bool | _Unset = ...) -> Mapped[bool]: ...
@overload
def boolean(
    *, nullable: Literal[True], default: bool | None | _Unset = ...
) -> Mapped[bool | None]: ...
def boolean(
    *,
    nullable: bool = False,
    default: bool | None | _Unset = _UNSET,
) -> Mapped[bool | None]:
    """``BOOLEAN`` column. Mirrors :meth:`Blueprint.boolean`."""
    kw: dict[str, Any] = {"nullable": nullable}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(Boolean(), **kw)


@overload
def datetime(
    *,
    timezone: bool = ...,
    nullable: Literal[False] = ...,
    default: _datetime | None | _Unset = ...,
    init: bool = ...,
) -> Mapped[_datetime]: ...
@overload
def datetime(
    *,
    timezone: bool = ...,
    nullable: Literal[True],
    default: _datetime | None | _Unset = ...,
    init: bool = ...,
) -> Mapped[_datetime | None]: ...
def datetime(
    *,
    timezone: bool = True,
    nullable: bool = False,
    default: _datetime | None | _Unset = _UNSET,
    init: bool = True,
) -> Mapped[_datetime | None]:
    """``TIMESTAMP``/``DATETIME`` column. Mirrors :meth:`Blueprint.datetime`.

    Defaults to ``timezone=True`` to match the framework convention (and the
    ``Timestamps`` mixin). Pass ``timezone=False`` for naive datetimes.
    Pass ``init=False`` to exclude from the dataclass ``__init__`` (e.g. for
    auto-populated audit columns like ``created_at`` / ``updated_at``).
    """
    kw: dict[str, Any] = {"nullable": nullable, "init": init}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(DateTime(timezone=timezone), **kw)


@overload
def json(
    *, nullable: Literal[False] = ..., init: bool = ..., default: object | _Unset = ...
) -> Mapped[Any]: ...
@overload
def json(
    *, nullable: Literal[True], init: bool = ..., default: object | _Unset = ...
) -> Mapped[Any]: ...
def json(
    *,
    nullable: bool = False,
    init: bool = True,
    default: object | _Unset = _UNSET,
) -> Mapped[Any]:
    """``JSON`` column. Mirrors :meth:`Blueprint.json`.

    The Python type is intentionally ``Any`` — JSON payload shape belongs to
    the boundary layer (Pydantic schema), not the storage layer. Pair this
    with ``PydanticType`` from :mod:`arvel.database.casts` when the payload
    has a fixed schema. Pass ``init=False`` for system-populated columns.
    """
    kw: dict[str, Any] = {"nullable": nullable, "init": init}
    _apply_json_default(kw, default)
    return mapped_column(_MutableJSONDict.as_mutable(JSON()), **kw)


@overload
def foreign_id(
    references: str,
    *,
    on_delete: str | None = ...,
    on_update: str | None = ...,
    nullable: Literal[False] = ...,
    index: bool = ...,
) -> Mapped[int]: ...
@overload
def foreign_id(
    references: str,
    *,
    on_delete: str | None = ...,
    on_update: str | None = ...,
    nullable: Literal[True],
    index: bool = ...,
) -> Mapped[int | None]: ...
def foreign_id(
    references: str,
    *,
    on_delete: str | None = None,
    on_update: str | None = None,
    nullable: bool = False,
    index: bool = True,
) -> Mapped[int | None]:
    """``INTEGER`` foreign key column. Mirrors :meth:`Blueprint.foreign_id`.

    The ``references`` argument is the target in ``"table.column"`` form::

        user_id: int = foreign_id("users.id", on_delete="CASCADE")

    Indexing defaults to ``True`` because joining on an un-indexed FK is the
    single most common application performance footgun.
    """
    return mapped_column(
        Integer,
        ForeignKey(references, ondelete=on_delete, onupdate=on_update),
        nullable=nullable,
        index=index,
    )


@overload
def foreign_uuid(
    references: str,
    *,
    on_delete: str | None = ...,
    on_update: str | None = ...,
    nullable: Literal[False] = ...,
    index: bool = ...,
) -> Mapped[_uuid.UUID]: ...
@overload
def foreign_uuid(
    references: str,
    *,
    on_delete: str | None = ...,
    on_update: str | None = ...,
    nullable: Literal[True],
    index: bool = ...,
) -> Mapped[_uuid.UUID | None]: ...
def foreign_uuid(
    references: str,
    *,
    on_delete: str | None = None,
    on_update: str | None = None,
    nullable: bool = False,
    index: bool = True,
) -> Mapped[_uuid.UUID | None]:
    """UUID foreign key column. Mirrors :func:`foreign_id` for UUID-keyed tables.

    Use when the referenced table uses :func:`uuid_id` as its primary key::

        cart_id: uuid.UUID = foreign_uuid("carts.id", on_delete="CASCADE")
        owner_id: uuid.UUID | None = foreign_uuid("users.id", nullable=True)

    When ``nullable=True`` the column defaults to ``None`` automatically.
    """
    kw: dict[str, Any] = {"nullable": nullable, "index": index}
    if nullable:
        kw["default"] = None
    return mapped_column(
        Uuid,
        ForeignKey(references, ondelete=on_delete, onupdate=on_update),
        **kw,
    )


@overload
def foreign_string(
    references: str,
    *,
    length: int = ...,
    on_delete: str | None = ...,
    on_update: str | None = ...,
    nullable: Literal[False] = ...,
    index: bool = ...,
) -> Mapped[str]: ...
@overload
def foreign_string(
    references: str,
    *,
    length: int = ...,
    on_delete: str | None = ...,
    on_update: str | None = ...,
    nullable: Literal[True],
    index: bool = ...,
) -> Mapped[str | None]: ...
def foreign_string(
    references: str,
    *,
    length: int = 36,
    on_delete: str | None = None,
    on_update: str | None = None,
    nullable: bool = False,
    index: bool = True,
) -> Mapped[str | None]:
    """``VARCHAR(length)`` foreign key column. The string-keyed sibling of :func:`foreign_id`.

    Use when the referenced table's primary key is a ``VARCHAR`` — e.g. a UUID
    stored as a string, or any natural string key. ``length`` defaults to 36 to
    match a canonical UUID string::

        user_id: Mapped[str] = foreign_string("users.id", on_delete="CASCADE")

    Like :func:`foreign_id`, indexing defaults to ``True`` — an un-indexed FK is
    the most common join footgun. When ``nullable=True`` the column defaults to
    ``None`` automatically.
    """
    kw: dict[str, Any] = {"nullable": nullable, "index": index}
    if nullable:
        kw["default"] = None
    return mapped_column(
        String(length=length),
        ForeignKey(references, ondelete=on_delete, onupdate=on_update),
        **kw,
    )


@overload
def decimal(
    precision: int = ...,
    scale: int = ...,
    *,
    nullable: Literal[False] = ...,
    default: Decimal | _Unset = ...,
) -> Mapped[Decimal]: ...
@overload
def decimal(
    precision: int = ...,
    scale: int = ...,
    *,
    nullable: Literal[True],
    default: Decimal | None | _Unset = ...,
) -> Mapped[Decimal | None]: ...
def decimal(
    precision: int = 10,
    scale: int = 2,
    *,
    nullable: bool = False,
    default: Decimal | None | _Unset = _UNSET,
) -> Mapped[Decimal | None]:
    """``NUMERIC(precision, scale)`` column. Mirrors :meth:`Blueprint.decimal`.

    Use for monetary amounts and other fixed-precision values::

        price: Decimal = decimal(10, 2)
        discount: Decimal | None = decimal(10, 2, nullable=True, default=None)
    """
    kw: dict[str, Any] = {"nullable": nullable}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(Numeric(precision=precision, scale=scale), **kw)


@overload
def jsonb(*, nullable: Literal[False] = ..., default: object | _Unset = ...) -> Mapped[Any]: ...
@overload
def jsonb(*, nullable: Literal[True], default: object | _Unset = ...) -> Mapped[Any]: ...
def jsonb(
    *,
    nullable: bool = False,
    default: object | _Unset = _UNSET,
) -> Mapped[Any]:
    """``JSONB`` column (PostgreSQL). Mirrors :meth:`Blueprint.jsonb`.

    Prefer over :func:`json` when using PostgreSQL — JSONB is stored binary,
    supports indexing (GIN), and enables containment/path operators::

        metadata: Mapped[Any] = jsonb(default=dict)
        slug: Mapped[Any] = jsonb()
    """
    kw: dict[str, Any] = {"nullable": nullable}
    _apply_json_default(kw, default)
    return mapped_column(_MutableJSONDict.as_mutable(JSONB()), **kw)


@overload
def enum(
    enum_type_or_values: type[_enum.Enum] | list[str] | tuple[str, ...],
    *,
    name: str | None = None,
    nullable: Literal[False] = ...,
    default: Any,
) -> Mapped[Any]: ...
@overload
def enum(
    enum_type_or_values: type[_enum.Enum] | list[str] | tuple[str, ...],
    *,
    name: str | None = None,
    nullable: Literal[True],
    default: Any,
) -> Mapped[Any]: ...
def enum(
    enum_type_or_values: type[_enum.Enum] | list[str] | tuple[str, ...],
    *,
    name: str | None = None,
    nullable: bool = False,
    default: Any = _UNSET,
) -> Mapped[Any]:
    """``ENUM`` column. Mirrors :meth:`Blueprint.enum`.

    Accepts a Python :class:`enum.Enum` subclass, a list, or a tuple of strings.
    When using string values on PostgreSQL, ``name`` must match the type name that
    the migration created (Blueprint convention: ``{tablename}_{colname}``)::

        class Status(str, enum.Enum):
            draft = "draft"
            published = "published"

        status: Status = enum(Status, default=Status.draft)
        theme: str = enum(["light", "dark", "system"], name="users_theme", default="system")

    Annotate with the concrete enum or ``str`` type; return type is ``Any``
    to avoid a generic type parameter on the helper.
    """
    if isinstance(enum_type_or_values, (list, tuple)):
        sa_type = Enum(*enum_type_or_values, name=name)
    else:
        sa_type = Enum(enum_type_or_values, name=name)
    kw: dict[str, Any] = {"nullable": nullable}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(sa_type, **kw)


def column(
    type_: TypeEngine[_T] | type[TypeEngine[_T]],
    *,
    primary_key: bool = False,
    nullable: bool = False,
    unique: bool = False,
    index: bool = False,
    init: bool = True,
    default: object = _UNSET,
    default_factory: Callable[[], Any] | None = None,
    server_default: Any = None,
) -> Mapped[_T]:
    """Column backed by an arbitrary SQLAlchemy type.

    The escape hatch for custom ``TypeDecorator`` types — ``EncryptedType``,
    ``PydanticType``, ``HashedType``, and friends — that the named helpers
    don't wrap, plus the place to declare a primary key or server default the
    named helpers don't cover. Keeps the same kwargs and ``Mapped[T]`` typing
    as the rest of the vocabulary, so models never reach for ``mapped_column``::

        api_key: Mapped[str] = column(EncryptedType(key_b64=os.environ["APP_KEY"]))
        profile: Mapped[Profile | None] = column(PydanticType(Profile), nullable=True, default=None)
        id: Mapped[str] = column(String(36), primary_key=True, init=False, default_factory=new_uuid)

    ``T`` is carried from the type's Python side, so ``EncryptedType`` (a
    ``TypeDecorator[str]``) yields ``Mapped[str]``. The return is ``Mapped[T]``;
    annotate the attribute ``Mapped[T | None]`` for a nullable column —
    ``Mapped`` is covariant, so that assignment is sound. The helper isn't
    overloaded on ``nullable`` on purpose: a ``Literal``-discriminated overload
    over a ``TypeVar`` defeats mypy's inference for ``nullable=True``.
    ``default`` is ``object`` for the same reason — keeping ``T`` out of every
    position but ``type_`` is what lets inference stay clean.
    """
    kw: dict[str, Any] = {
        "primary_key": primary_key,
        "nullable": nullable,
        "unique": unique,
        "index": index,
        "init": init,
    }
    if not isinstance(default, _Unset):
        kw["default"] = default
    if default_factory is not None:
        kw["default_factory"] = default_factory
    if server_default is not None:
        kw["server_default"] = server_default
    return mapped_column(type_, **kw)


def nullable_column(
    type_: TypeEngine[Any] | type[TypeEngine[Any]],
    *,
    unique: bool = False,
    index: bool = False,
    init: bool = True,
    default: object = _UNSET,
) -> Mapped[Any]:
    """Nullable column backed by any SQLAlchemy type — the ``| None`` sibling of :func:`column`.

    Use when the attribute is annotated ``Mapped[T | None]``::

        tokens: Mapped[dict[str, Any] | None] = nullable_column(EncryptedJson(), default=None)

    Returns ``Mapped[Any]`` on purpose — exactly like SQLAlchemy's own
    ``mapped_column`` — so the ``Mapped[T | None]`` attribute annotation is the
    source of truth for the Python type. A generic ``Mapped[T | None]`` return
    can't work here: ``Mapped`` is covariant, so mypy fixes ``T`` from the
    annotation and then rejects ``type_``. The non-null :func:`column` stays
    generic because there's no ``| None`` to trip that inference.
    """
    kw: dict[str, Any] = {"nullable": True, "unique": unique, "index": index, "init": init}
    if not isinstance(default, _Unset):
        kw["default"] = default
    return mapped_column(type_, **kw)


def tsvector(*, nullable: bool = True) -> Mapped[str | None]:
    """PostgreSQL ``TSVECTOR`` column for full-text search.

    Almost always nullable — a freshly inserted row has no search vector
    until the background trigger or update fires::

        search_vector: str | None = tsvector()
    """
    return mapped_column(TSVECTOR, nullable=nullable, default=None, init=False)
