"""``Model`` base + ``ActiveRecord`` / ``Timestamps`` / ``SoftDeletes`` mixins."""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, contextmanager, suppress
from contextvars import ContextVar
from dataclasses import InitVar
from datetime import UTC, date
from datetime import datetime as _datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from functools import partial, wraps
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    NamedTuple,
    Protocol,
    Self,
    TypeGuard,
    TypeVar,
    cast,
    dataclass_transform,
    get_origin,
    overload,
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
from sqlalchemy.orm.base import NO_VALUE
from sqlalchemy.orm.decl_api import DCTransformDeclarative

from arvel.database.attributes import CastsAttributes
from arvel.database.columns import (
    big_integer,
    boolean,
    column,
    datetime,
    decimal,
    enum,
    foreign_id,
    foreign_string,
    foreign_uuid,
    id_,
    integer,
    json,
    jsonb,
    nullable_column,
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
    UnknownRelationError,
)
from arvel.database.query_mixin import QueryMixin
from arvel.database.session import get_active_session
from arvel.support.str import Str

if TYPE_CHECKING:
    from arvel.database.collection import ModelCollection
    from arvel.database.orm.relations import (
        Ancestors,
        BelongsTo,
        Descendants,
        HasMany,
        HasOne,
    )

ModelT = TypeVar("ModelT", bound="Model")
RelatedT = TypeVar("RelatedT", bound="Model")
SchemaT = TypeVar("SchemaT", bound=BaseModel)


def _json_cast(value: Any) -> Any:
    """Decode ``value`` from JSON if it's a string, otherwise return as-is."""
    import json

    return json.loads(value) if isinstance(value, str) else value


def _object_cast(value: Any) -> Any:
    """Decode a JSON object into attribute-accessible form (Laravel's ``object`` cast)."""
    import json
    from types import SimpleNamespace

    if isinstance(value, str):
        return json.loads(value, object_hook=lambda d: SimpleNamespace(**d))
    if isinstance(value, dict):
        return SimpleNamespace(**value)
    return value


def _collection_cast(value: Any) -> Any:
    """Decode a JSON array/object into an Arvel ``Collection`` (Laravel's ``collection`` cast)."""
    import json

    from arvel.support.collections import Collection

    data = json.loads(value) if isinstance(value, str) else value
    return Collection(data if data is not None else [])


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


# argon2 ("$argon2…") and bcrypt ("$2…") digests — treat as already-hashed.
_HASH_PREFIXES = ("$argon2", "$2")


def _hashed_cast(value: Any) -> str:
    """Hash on write via the Hash facade; pass an existing digest through unchanged."""
    from arvel.facades.hash import Hash

    text_value = value if isinstance(value, str) else str(value)
    if text_value.startswith(_HASH_PREFIXES):
        return text_value
    return Hash.make(text_value)


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
    "hashed": _hashed_cast,
    "object": _object_cast,
    "collection": _collection_cast,
}
_VALID_CASTS: frozenset[str] = frozenset(_CAST_DISPATCH)


def _object_serialize(value: Any) -> Any:
    if hasattr(value, "__dict__"):
        result: dict[str, Any] = dict(value.__dict__)
        return result
    return value


# Read-only serializers for built-ins whose read value isn't JSON-friendly.
_BUILTIN_SERIALIZERS: dict[str, Callable[[Any], Any]] = {
    "object": _object_serialize,
    "collection": list,
}

# JSON collection casts stay read-path only on write — coercing to dict/list in
# memory breaks String-column INSERTs. Use TypeDecorator for column-level JSON.
_WRITE_SKIP_CASTS: frozenset[str] = frozenset({"dict", "list", "array", "object", "collection"})

# Write-only casts: applied on assignment, never on read. `hashed` would corrupt a
# stored digest if re-hashed on every attribute access.
_READ_SKIP_CASTS: frozenset[str] = frozenset({"hashed"})

# A cast spec is a built-in name ("boolean"), a parameterized name ("decimal:2"),
# or a CastsAttributes class/instance.
_CastFn = Callable[[Any, str, Any], Any]


class _ResolvedCast(NamedTuple):
    """Per-field cast pipeline, computed once at class definition. None = passthrough."""

    read: _CastFn | None
    write: _CastFn | None
    serialize: _CastFn | None


def _make_decimal_cast(scale: int) -> Callable[[Any], Decimal]:
    quantum = Decimal(1).scaleb(-scale)

    def _coerce(value: Any) -> Decimal:
        return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)

    return _coerce


def _value_only(coercer: Callable[[Any], Any], _model: Any, _key: str, value: Any) -> Any:
    """Adapt a value->value built-in coercer to the (model, key, value) cast signature."""
    return coercer(value)


def _make_enum_cast(enum_cls: type[Enum]) -> _ResolvedCast:
    """Read → enum member, write → backing value, serialize → backing value."""

    def read(_model: Any, _key: str, value: Any) -> Any:
        return value if isinstance(value, enum_cls) else enum_cls(value)

    def write(_model: Any, _key: str, value: Any) -> Any:
        if isinstance(value, enum_cls):
            return value.value
        # Accept either a backing value or a member name; store the backing value.
        return enum_cls(value).value

    def serialize(_model: Any, _key: str, value: Any) -> Any:
        return value.value if isinstance(value, Enum) else value

    return _ResolvedCast(read=read, write=write, serialize=serialize)


def _shape_decoded(kind: str, decoded: Any) -> Any:
    """Wrap a JSON-decoded value into the shape an encrypted cast variant exposes."""
    if kind == "object":
        from types import SimpleNamespace

        return SimpleNamespace(**decoded) if isinstance(decoded, dict) else decoded
    if kind == "collection":
        from arvel.support.collections import Collection

        return Collection(decoded if decoded is not None else [])
    return decoded


def _make_encrypted_cast(param: str) -> _ResolvedCast:
    """``encrypted[:json|array|object|collection]`` — AES-GCM via the Crypt facade.

    Reads decrypt (and decode); writes encrypt (and encode). ``to_dict`` exposes the
    decrypted value, matching Eloquent's ``toArray``.
    """
    kind = param or "string"
    if kind not in ("string", "json", "array", "object", "collection"):
        raise ValueError(
            f"'encrypted:{param}' is not a recognised encrypted cast variant "
            "(use one of: string, json, array, object, collection)."
        )

    def read(_model: Any, _key: str, value: Any) -> Any:
        from arvel.facades.crypt import Crypt

        if kind == "string":
            return Crypt.decrypt_string(value)
        return _shape_decoded(kind, Crypt.decrypt(value))

    def write(_model: Any, _key: str, value: Any) -> Any:
        from arvel.facades.crypt import Crypt

        if kind == "string":
            return Crypt.encrypt_string(value if isinstance(value, str) else str(value))
        # SimpleNamespace isn't JSON-serializable; unwrap it. dict/list pass straight
        # through (Collection is a list subclass, so json.dumps handles it).
        payload: Any = value
        if hasattr(value, "__dict__") and not isinstance(value, (dict, list)):
            payload = dict(value.__dict__)
        return Crypt.encrypt(payload)

    serialize = None
    if kind == "object":
        serialize = partial(_value_only, _object_serialize)
    elif kind == "collection":
        serialize = partial(_value_only, list)
    return _ResolvedCast(read=read, write=write, serialize=serialize)


def _make_datetime_format_cast(fmt: str) -> _ResolvedCast:
    """``datetime:FORMAT`` — read coerces to datetime, serialize emits ``strftime(FORMAT)``."""

    def read(_model: Any, _key: str, value: Any) -> Any:
        if isinstance(value, str):
            try:
                parsed = _datetime.strptime(value, fmt)  # noqa: DTZ007 — tz applied below
            except ValueError:
                return _to_utc_datetime(value)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        return _to_utc_datetime(value)

    def serialize(model: Any, key: str, value: Any) -> Any:
        dt = read(model, key, value)
        return dt.strftime(fmt) if isinstance(dt, _datetime) else value

    return _ResolvedCast(read=read, write=read, serialize=serialize)


def _resolve_cast_spec(model_name: str, field: str, spec: Any) -> _ResolvedCast:
    if isinstance(spec, CastsAttributes):
        return _ResolvedCast(read=spec.get, write=spec.set, serialize=spec.serialize)
    if isinstance(spec, type) and issubclass(spec, CastsAttributes):
        built = spec()
        return _ResolvedCast(read=built.get, write=built.set, serialize=built.serialize)
    if isinstance(spec, type) and issubclass(spec, Enum):
        return _make_enum_cast(spec)
    if isinstance(spec, str):
        return _resolve_string_cast(model_name, field, spec)
    raise TypeError(
        f"{model_name}.__casts__['{field}']: cast spec must be a str, an Enum class, or a "
        f"CastsAttributes class/instance, got {type(cast('object', spec)).__name__}."
    )


def _resolve_string_cast(model_name: str, field: str, spec: str) -> _ResolvedCast:
    base, sep, param = spec.partition(":")
    if base == "encrypted":
        return _make_encrypted_cast(param)
    if sep:
        if base == "decimal":
            both = partial(_value_only, _make_decimal_cast(int(param)))
            return _ResolvedCast(read=both, write=both, serialize=None)
        if base == "datetime":
            return _make_datetime_format_cast(param)
        raise ValueError(
            f"{model_name}.__casts__['{field}'] = '{spec}': "
            f"'{base}' takes no parameter or is not a parameterized cast."
        )
    coercer = _CAST_DISPATCH.get(base)
    if coercer is None:
        raise ValueError(
            f"{model_name}.__casts__['{field}'] = '{spec}' is not a recognised cast "
            f"type. Valid: {sorted(_VALID_CASTS)} (or a CastsAttributes subclass)."
        )
    read = None if base in _READ_SKIP_CASTS else partial(_value_only, coercer)
    write = None if base in _WRITE_SKIP_CASTS else partial(_value_only, coercer)
    serializer = _BUILTIN_SERIALIZERS.get(base)
    serialize = partial(_value_only, serializer) if serializer is not None else None
    return _ResolvedCast(read=read, write=write, serialize=serialize)


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

_RECURSIVE_RETURN_NAMES = frozenset({"Descendants", "Ancestors"})
_RELATION_RETURN_NAMES = frozenset({"HasMany", "HasOne", "BelongsTo"}) | _RECURSIVE_RETURN_NAMES

# The builder methods on Model return relation types from a zero-positional-arg
# signature too — exclude them by name so they're not mistaken for accessors.
_RELATION_BUILDER_NAMES = frozenset(
    {"has_many", "has_one", "belongs_to", "has_many_recursive", "belongs_to_recursive"}
)

# CPython code-flag bits: 0x04 = *args, 0x08 = **kwargs.
_VARARGS_OR_KWARGS = 0x04 | 0x08


def _relation_method_kind(value: Any) -> str | None:
    """Return the relation type name when *value* is a zero-arg relation accessor.

    A relation accessor is a plain instance method taking only ``self`` whose
    return annotation is ``HasMany`` / ``HasOne`` / ``BelongsTo`` / ``Descendants``
    / ``Ancestors``. The framework's own ``has_many``/``belongs_to_recursive``/...
    builders are excluded by name — only Laravel-style accessors like
    ``def orders(self)`` or ``def descendants(self)`` match.
    """
    if isinstance(value, (staticmethod, classmethod)) or not callable(value):
        return None
    if getattr(value, "__name__", None) in _RELATION_BUILDER_NAMES:
        return None
    code = getattr(value, "__code__", None)
    if code is None or code.co_argcount != 1 or (code.co_flags & _VARARGS_OR_KWARGS):
        return None
    annotation = getattr(value, "__annotations__", {}).get("return")
    if annotation is None:
        return None
    if isinstance(annotation, str):
        head = annotation.split("[", 1)[0].rsplit(".", 1)[-1].strip()
    else:
        origin = get_origin(annotation) or annotation
        head = getattr(origin, "__name__", "")
    return head if head in _RELATION_RETURN_NAMES else None


def _wrap_relation_method(name: str, fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Tag the builder a relation accessor returns with its accessor name.

    Lets ``await u.orders().get()`` serve eager-loaded rows from the owner's cache
    after ``with_("orders")``. ``wraps`` keeps the original signature/annotations,
    so static type checkers still see ``-> HasMany[Order]``.
    """

    @wraps(fn)
    def wrapper(self: Any) -> Any:
        rel = fn(self)
        with suppress(AttributeError):
            rel._relation_name = name
        return rel

    return wrapper


def _register_relation_methods(
    bases: tuple[type, ...], namespace: dict[str, Any]
) -> dict[str, Any]:
    """Wrap zero-arg relation accessors + record their names for the eager engine.

    Returns the (possibly updated) namespace. Inherited accessor names carry over.
    """
    fk_relations: set[str] = set()
    recursive_relations: set[str] = set()
    for base in bases:
        fk_relations |= set(getattr(base, "__arvel_fk_relations__", ()))
        recursive_relations |= set(getattr(base, "__arvel_recursive_relations__", ()))
    wrapped: dict[str, Any] = {}
    for attr_name, value in namespace.items():
        kind = _relation_method_kind(value)
        if kind is None:
            continue
        wrapped[attr_name] = _wrap_relation_method(attr_name, value)
        if kind in _RECURSIVE_RETURN_NAMES:
            recursive_relations.add(attr_name)
        else:
            fk_relations.add(attr_name)
    if not wrapped and not fk_relations and not recursive_relations:
        return namespace
    return {
        **namespace,
        **wrapped,
        "__arvel_fk_relations__": frozenset(fk_relations),
        "__arvel_recursive_relations__": frozenset(recursive_relations),
    }


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
        column,
        datetime,
        decimal,
        enum,
        foreign_id,
        foreign_string,
        foreign_uuid,
        integer,
        json,
        jsonb,
        nullable_column,
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

        # Wrap method-style FK relation accessors (has_many/has_one/belongs_to) so
        # they're eager-loadable via with_("name") and serve cached results on read-back.
        namespace = _register_relation_methods(bases, namespace)

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


def _resolve_related_model(owner_cls: type[Any], related: type[Any] | str) -> type[Any]:
    """Resolve a related model given as a class or its class-name string.

    String targets let bidirectional relations skip the import — the same reason
    Eloquent and SQLAlchemy ``relationship()`` accept class-name strings.
    """
    if not isinstance(related, str):
        return related
    for mapper in owner_cls.registry.mappers:
        if mapper.class_.__name__ == related:
            return cast("type[Any]", mapper.class_)
    raise UnknownRelationError(owner_cls.__name__, related)


# Task-local switch for Model.unguarded(): suspends mass-assignment checks.
_mass_assignment_unguarded: ContextVar[bool] = ContextVar("arvel_unguarded", default=False)

# Task-local switch for Model.without_timestamps(): the before_insert/before_update
# hooks read it, so timestamp auto-fill is skipped for writes inside the block.
_suppress_timestamps: ContextVar[bool] = ContextVar("arvel_suppress_timestamps", default=False)


@asynccontextmanager
async def _without_timestamps() -> AsyncGenerator[None]:
    """Mute timestamp auto-fill for writes in the block. Re-entrant, task-local."""
    token = _suppress_timestamps.set(True)
    try:
        yield
    finally:
        _suppress_timestamps.reset(token)


def _check_mass_assignment(model_cls: type[Any], attrs: dict[str, Any]) -> None:
    """Enforce __fillable__ / __guarded__ on create()/update() calls."""
    if _mass_assignment_unguarded.get():
        return
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

    # Lifecycle name -> ModelEvent subclass, dispatched on the app event bus
    # when that lifecycle fires (Eloquent's $dispatchesEvents). None unless declared.
    __dispatches_events__: ClassVar[dict[str, type[Any]] | None] = None
    # Observer classes auto-registered at class-definition time (Eloquent's #[ObservedBy]).
    __observed_by__: ClassVar[list[type[Any]] | None] = None

    # Names of parent relation accessor methods whose timestamps get bumped on save.
    # Eloquent's $touches. Each entry is a method returning a BelongsTo builder.
    __touches__: ClassVar[tuple[str, ...]] = ()

    # Method-style FK relation accessor names (has_many/has_one/belongs_to),
    # populated per-class by _ModelMeta. The eager engine reads this to recognize
    # which methods are eager-loadable via with_("name").
    __arvel_fk_relations__: ClassVar[frozenset[str]] = frozenset()
    # Self-referential recursive relation accessor names (descendants/ancestors),
    # populated per-class by _ModelMeta. Eager-loadable via with_tree("name").
    __arvel_recursive_relations__: ClassVar[frozenset[str]] = frozenset()

    # Timestamp controls (Eloquent parity). Set __timestamps__ = False to opt out;
    # point CREATED_AT/UPDATED_AT at custom columns. Auto-fill hooks attach in
    # __init_subclass__ only when the named attributes actually exist on the model.
    __timestamps__: ClassVar[bool] = True
    CREATED_AT: ClassVar[str] = "created_at"
    UPDATED_AT: ClassVar[str] = "updated_at"

    # Set per-instance at save time: column keys changed by the last save.
    _arvel_changed: ClassVar[frozenset[str] | None] = None

    # Column name -> mutator fn, collected from @mutator-decorated methods across
    # the MRO in __init_subclass__. Empty unless a subclass declares one.
    __arvel_mutators__: ClassVar[dict[str, Callable[[Any, Any], Any]]] = {}

    # Field -> resolved cast pipeline, built from __casts__ in __init_subclass__.
    __arvel_cast_resolvers__: ClassVar[dict[str, _ResolvedCast]] = {}

    # Per-instance override set by make_hidden() / make_visible().
    # ClassVar keeps it out of MappedAsDataclass field processing and ORM column
    # mapping.  Instances get their own list via object.__setattr__ on first use.
    _instance_hidden: ClassVar[list[str] | None] = None
    # Per-instance accessor names added to to_dict() via append() / set_appends().
    _instance_appends: ClassVar[list[str] | None] = None

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

    @classmethod
    def without_events(cls) -> AbstractAsyncContextManager[None]:
        """Mute lifecycle observers for the duration of an ``async with`` block."""
        from arvel.database.events import without_events as _without_events

        return _without_events()

    @classmethod
    @contextmanager
    def unguarded(cls) -> Generator[None]:
        """Suspend mass-assignment guards for the block (re-entrant). Trusted input only."""
        token = _mass_assignment_unguarded.set(True)
        try:
            yield
        finally:
            _mass_assignment_unguarded.reset(token)

    def fill(self, **attrs: Any) -> Any:
        """Mass-assign attributes in place, honouring fillable/guarded and mutators."""
        _check_mass_assignment(type(self), attrs)
        for key, value in attrs.items():
            setattr(self, key, value)
        return self

    def force_fill(self, **attrs: Any) -> Any:
        """Mass-assign every attribute, bypassing fillable/guarded. Trusted input only."""
        for key, value in attrs.items():
            setattr(self, key, value)
        return self

    def _arvel_column_keys(self) -> list[str]:
        mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(type(self)))
        return [c.key for c in mapper.column_attrs]

    def _read_cast(self, key: str, raw: Any) -> Any:
        if raw is None or raw is NO_VALUE:
            return raw
        resolved = type(self).__arvel_cast_resolvers__.get(key)
        if resolved is not None and resolved.read is not None:
            return resolved.read(self, key, raw)
        return raw

    def original_is_equivalent(self, key: str) -> bool:
        """True when ``key``'s pending value equals its original *cast* value.

        Mirrors Eloquent's ``originalIsEquivalent``: ``"1"`` vs ``1``, a re-serialized
        JSON string, or an equal decimal in a different form don't count as dirty.
        """
        state = sqla_inspect(self)
        if state is None:
            return True
        if key not in state.attrs or not state.attrs[key].history.has_changes():
            return True
        original_raw = state.committed_state.get(key, NO_VALUE)
        current_raw = object.__getattribute__(self, key)
        # NO_VALUE = pending/unflushed with no committed original → genuinely dirty.
        if original_raw is NO_VALUE or current_raw is NO_VALUE:
            return False
        if current_raw == original_raw:
            return True
        if current_raw is None or original_raw is None:
            return False
        return bool(self._read_cast(key, current_raw) == self._read_cast(key, original_raw))

    def is_dirty(self, *attributes: str) -> bool:
        """True if any (or any of the named) column attributes have unsaved changes."""
        state = sqla_inspect(self)
        if state is None:
            return False
        keys = list(attributes) if attributes else self._arvel_column_keys()
        return any(
            k in state.attrs
            and state.attrs[k].history.has_changes()
            and not self.original_is_equivalent(k)
            for k in keys
        )

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
            if k in state.attrs
            and state.attrs[k].history.has_changes()
            and not self.original_is_equivalent(k)
        }

    def get_raw_original(self, key: str | None = None, default: Any = None) -> Any:
        """Pre-cast value(s) as loaded from the DB (or last save), ignoring pending changes."""
        state = sqla_inspect(self)
        if state is None:
            return default if key is not None else {}
        if key is not None:
            if key in state.committed_state:
                return state.committed_state[key]
            return getattr(self, key, default)
        return {
            k: state.committed_state.get(k, getattr(self, k)) for k in self._arvel_column_keys()
        }

    def get_original(self, key: str | None = None, default: Any = None) -> Any:
        """Original value(s), cast like Eloquent's ``getOriginal``. See ``get_raw_original``."""
        raw = self.get_raw_original(key, default)
        if key is not None:
            return self._read_cast(key, raw) if raw is not default else raw
        return {k: self._read_cast(k, v) for k, v in raw.items()}

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
        await self._touch_parents()
        return self

    async def _touch_parents(self) -> None:
        """Bump UPDATED_AT on each parent named in ``__touches__`` (Eloquent's $touches)."""
        for name in type(self).__touches__:
            accessor = getattr(self, name, None)
            if accessor is None:
                continue
            builder = accessor()
            parent = await builder.first()
            if parent is not None:
                await parent.touch()

    async def push(self) -> Any:
        """Save this model plus every loaded relation (and their loaded relations).

        Eloquent's ``push``: persists the model, then cascades save() across the
        already-loaded relationships so pending edits on related rows go down too.
        """
        await self._push(set())
        return self

    async def _push(self, visited: set[int]) -> None:
        # Bidirectional loaded graphs (user.posts <-> post.author) would recurse
        # forever without a per-call visited set keyed on object identity.
        if id(self) in visited:
            return
        visited.add(id(self))
        await self.save()
        state = sqla_inspect(self)
        if state is None:
            return
        for rel in state.mapper.relationships:
            if rel.key not in state.dict:
                continue
            value = state.dict[rel.key]
            related = value if rel.uselist else ([value] if value is not None else [])
            for item in related:
                if isinstance(item, Model):
                    await item._push(visited)
        # Method-style FK relations live in the per-instance eager cache, not on
        # the mapper, so cascade over those too.
        for cached in vars(self).get("__arvel_eager_relations__", {}).values():
            for item in cached:
                if isinstance(item, Model):
                    await item._push(visited)

    async def delete(self) -> Any:
        from arvel.database.events import fire_after_commit, fire_async, fire_cancellable

        soft_field = getattr(type(self), "__arvel_soft_delete_column__", None)
        session = get_active_session()
        await fire_cancellable(type(self), "deleting", self)
        if soft_field:
            setattr(self, soft_field, _datetime.now(UTC))
            session.add(self)
            await session.flush()
            # `trashed` distinguishes a soft delete from a hard one; `deleted` fires for both.
            await fire_async(type(self), "trashed", self)
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
        # Laravel order: force_deleting, deleting, hard delete, deleted, force_deleted.
        # Either before-hook can abort. `trashed` never fires — this is a hard delete.
        await fire_cancellable(type(self), "force_deleting", self)
        await fire_cancellable(type(self), "deleting", self)
        await session.delete(self)
        await session.flush()
        await fire_async(type(self), "deleted", self)
        await fire_async(type(self), "force_deleted", self)
        fire_after_commit(type(self), self)
        return self

    def trashed(self) -> bool:
        """True when this instance is soft-deleted (``deleted_at`` is set)."""
        soft_field = getattr(type(self), "__arvel_soft_delete_column__", None)
        return soft_field is not None and getattr(self, soft_field, None) is not None

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

    async def save_quietly(self) -> Any:
        from arvel.database.events import without_events

        async with without_events():
            return await self.save()

    async def delete_quietly(self) -> Any:
        from arvel.database.events import without_events

        async with without_events():
            return await self.delete()

    async def force_delete_quietly(self) -> Any:
        from arvel.database.events import without_events

        async with without_events():
            return await self.force_delete()

    async def restore_quietly(self) -> Any:
        from arvel.database.events import without_events

        async with without_events():
            return await self.restore()

    async def update_quietly(self, **attrs: Any) -> Any:
        from arvel.database.events import without_events

        async with without_events():
            self.fill(**attrs)
            return await self.save()

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

    async def touch(self, attribute: str | None = None) -> Any:
        """Set a timestamp column to now and save (default: ``UPDATED_AT``).

        Fires lifecycle events through ``save()``; pass an ``attribute`` to bump an
        arbitrary column (e.g. ``touch("published_at")``).
        """
        column = attribute or type(self).UPDATED_AT
        if hasattr(self, column):
            object.__setattr__(self, column, _datetime.now(UTC))
        return await self.save()

    async def touch_quietly(self, attribute: str | None = None) -> Any:
        """Like ``touch()`` but without firing lifecycle events."""
        from arvel.database.events import without_events

        async with without_events():
            return await self.touch(attribute)

    @classmethod
    def without_timestamps(cls) -> AbstractAsyncContextManager[None]:
        """Skip timestamp auto-fill for writes inside the ``async with`` block."""
        return _without_timestamps()

    async def replicate(self, *, except_: list[str] | None = None) -> Any:
        """Return an unsaved copy of this model, excluding ``except_`` fields.

        Fires ``replicating`` on the clone before returning it.
        """
        from arvel.database.events import fire_async

        mapper = sqla_inspect(type(self))
        if mapper is None:
            raise RuntimeError(f"{type(self).__name__} is not a mapped SQLA class.")
        import inspect

        skip = set(except_ or [])
        # Eloquent drops the PK and timestamps on a fresh copy; don't carry over a
        # soft-delete flag either, or the clone would start life already trashed.
        skip.update(
            {
                getattr(type(self), "CREATED_AT", "created_at"),
                getattr(type(self), "UPDATED_AT", "updated_at"),
            }
        )
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
        clone = cast("Any", type(self))(**attrs)
        await fire_async(type(self), "replicating", clone)
        return clone

    async def load(self, *relations: str) -> None:
        """Lazy-load relations onto this already-fetched instance.

        SQLAlchemy relationships go through selectinload; async descriptor
        relations (BelongsToMany / MorphToMany / MorphOne / MorphMany) batch-load
        into the per-instance eager cache so their accessors serve from it.
        """
        from arvel.database.query import is_async_relation, load_async_relation_path

        async_rels = [r for r in relations if is_async_relation(type(self), r)]
        sa_rels = [r for r in relations if r not in async_rels]

        for rel in async_rels:
            await load_async_relation_path(type(self), [self], rel, None)

        if not sa_rels:
            return

        from sqlalchemy.orm import selectinload

        session = get_active_session()
        mapper = sqla_inspect(type(self))
        if mapper is None:
            return
        # Expire the requested relations so SQLAlchemy's selectinload will
        # replace them even when expire_on_commit=False is in use.
        session.expire(self, sa_rels)
        pk_cols = mapper.primary_key
        pk_values = tuple(getattr(self, col.key) for col in pk_cols)
        stmt = select(type(self))
        for col, val in zip(pk_cols, pk_values, strict=True):
            stmt = stmt.where(col == val)
        for rel in sa_rels:
            rel_attr = getattr(type(self), rel, None)
            if rel_attr is not None:
                stmt = stmt.options(selectinload(rel_attr))
        result = await session.execute(stmt)
        fresh = result.scalars().first()
        if fresh is not None:
            for rel in sa_rels:
                loaded = getattr(fresh, rel, None)
                if loaded is not None:
                    object.__setattr__(self, rel, loaded)

    async def load_missing(self, *relations: str) -> None:
        """Load each relation only if not already populated on this instance."""
        state = sqla_inspect(self)
        to_load = [r for r in relations if r in (state.unloaded if state else set())]
        if to_load:
            await self.load(*to_load)

    async def load_aggregate(
        self,
        relation: str,
        agg: str,
        column: str | None = None,
        *,
        alias: str | None = None,
        constraint: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Compute an aggregate over a relation, cache it on this instance, and return it.

        ``relation`` may carry an ``" as <alias>"`` suffix; an explicit ``alias`` wins.
        """
        from arvel.database.query import load_aggregate_for

        return await load_aggregate_for(
            self, relation, agg, column, alias=alias, constraint=constraint
        )

    async def load_count(
        self, relation: str, *, constraint: Callable[[Any], Any] | None = None
    ) -> Any:
        """Count a relation's rows and cache the result as ``{relation}_count``."""
        return await self.load_aggregate(relation, "count", constraint=constraint)

    async def load_sum(
        self, relation: str, column: str, *, constraint: Callable[[Any], Any] | None = None
    ) -> Any:
        """Sum a relation column and cache it as ``{relation}_sum_{column}``."""
        return await self.load_aggregate(relation, "sum", column, constraint=constraint)

    async def load_exists(
        self, relation: str, *, constraint: Callable[[Any], Any] | None = None
    ) -> Any:
        """Check whether a relation has any rows; cache it as ``{relation}_exists``."""
        return await self.load_aggregate(relation, "exists", constraint=constraint)

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

    def make_hidden_if(self, condition: bool | Callable[[Any], bool], *fields: str) -> Any:
        """Hide ``fields`` only when ``condition`` (a bool or ``self``-predicate) holds."""
        if condition(self) if callable(condition) else condition:
            self.make_hidden(*fields)
        return self

    def make_visible_if(self, condition: bool | Callable[[Any], bool], *fields: str) -> Any:
        """Unhide ``fields`` only when ``condition`` (a bool or ``self``-predicate) holds."""
        if condition(self) if callable(condition) else condition:
            self.make_visible(*fields)
        return self

    def append(self, *attributes: str) -> Any:
        """Add accessor names to this instance's serialized output (Eloquent's append)."""
        current = list(getattr(self, "_instance_appends", None) or [])
        for name in attributes:
            if name not in current:
                current.append(name)
        object.__setattr__(self, "_instance_appends", current)
        return self

    def set_appends(self, attributes: list[str]) -> Any:
        """Replace this instance's appended-accessor list."""
        object.__setattr__(self, "_instance_appends", list(attributes))
        return self

    def _collect_appends(self) -> list[str]:
        """Class-level ``__appends__`` merged with per-instance appends, de-duped."""
        appends: list[str] = list(type(self).__appends__ or [])
        for name in self._instance_appends or []:
            if name not in appends:
                appends.append(name)
        return appends

    def only(self, *keys: str) -> dict[str, Any]:
        """Subset of ``to_dict()`` limited to ``keys`` (missing keys are skipped)."""
        data = self.to_dict()
        return {k: data[k] for k in keys if k in data}

    def except_(self, *keys: str) -> dict[str, Any]:
        """``to_dict()`` with ``keys`` removed."""
        data = self.to_dict()
        return {k: v for k, v in data.items() if k not in keys}

    @classmethod
    def get_key_name(cls) -> str:
        """Name of the primary-key column. Raises for composite keys."""
        mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(cls))
        pk_cols = mapper.primary_key
        if len(pk_cols) != 1:
            raise TypeError(f"{cls.__name__} has a composite primary key; use get_key().")
        key = pk_cols[0].key
        if key is None:
            raise TypeError(f"{cls.__name__} primary key column has no key.")
        return key

    def get_key(self) -> Any:
        """Primary-key value. Returns a tuple for composite keys."""
        mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(type(self)))
        pk_cols = mapper.primary_key
        keys = [c.key for c in pk_cols if c.key is not None]
        if len(keys) == 1:
            return getattr(self, keys[0])
        return tuple(getattr(self, k) for k in keys)

    @classmethod
    def qualify_column(cls, column: str) -> str:
        """Prefix ``column`` with the table name: ``"users.email"``."""
        from sqlalchemy import Table

        mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(cls))
        table = mapper.local_table
        table_name = table.name if isinstance(table, Table) else str(table)
        return f"{table_name}.{column}"

    @classmethod
    def get_morph_class(cls) -> str:
        """Polymorphic type token for this model: its morph-map alias, else short name."""
        from arvel.database.orm.morph_map import get_morph_alias

        return get_morph_alias(cls)

    def is_same(self, other: Any) -> bool:
        """True when ``other`` is the same model type with the same (non-null) key."""
        if other is None or type(self) is not type(other):
            return False
        key = self.get_key()
        return key is not None and key == other.get_key()

    def is_not(self, other: Any) -> bool:
        """Inverse of :meth:`is_same`."""
        return not self.is_same(other)

    def discard_changes(self) -> Any:
        """Revert pending attribute changes back to the loaded/last-saved values."""
        state = sqla_inspect(self)
        if state is None:
            return self
        for key in self._arvel_column_keys():
            if (
                key in state.attrs
                and state.attrs[key].history.has_changes()
                and key in state.committed_state
            ):
                setattr(self, key, state.committed_state[key])
        return self

    def to_dict(self) -> dict[str, Any]:
        mapper = sqla_inspect(type(self))
        if mapper is None:
            raise RuntimeError(f"{type(self).__name__} is not a mapped SQLA class.")
        # Build the base dict
        data = {col.key: getattr(self, col.key) for col in mapper.column_attrs}
        # Let custom casts shape their serialized form (Eloquent's SerializesCastable).
        resolvers = type(self).__arvel_cast_resolvers__
        if resolvers:
            for key, resolved in resolvers.items():
                if resolved.serialize is not None and data.get(key) is not None:
                    data[key] = resolved.serialize(self, key, data[key])
        # Append @accessor-backed computed attributes (Eloquent's $appends),
        # plus any added per-instance via append() / set_appends().
        for name in self._collect_appends():
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
                if not k.startswith("_sa_") and k not in ("_instance_hidden", "_arvel_attr_cache")
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
        # Resolve + validate __casts__ once at class-definition time.
        casts: dict[str, Any] | None = getattr(cls, "__casts__", None)
        if casts:
            cls.__arvel_cast_resolvers__ = {
                field_name: _resolve_cast_spec(cls.__name__, field_name, spec)
                for field_name, spec in casts.items()
            }

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

        # Auto-register observers declared on this class via __observed_by__.
        observed_by: list[type[Any]] | None = cls.__dict__.get("__observed_by__")
        if observed_by:
            from arvel.database.events import bind_observer

            for observer in observed_by:
                bind_observer(cls, observer)

        # Attach timestamp auto-fill hooks when the model actually has the columns
        # named by CREATED_AT/UPDATED_AT. Works for the Timestamps mixin and for
        # models declaring their own custom timestamp columns.
        if getattr(cls, "__timestamps__", True):
            created = getattr(cls, "CREATED_AT", "created_at")
            updated = getattr(cls, "UPDATED_AT", "updated_at")
            if hasattr(cls, created) or hasattr(cls, updated):
                event.listen(cls, "before_insert", _set_timestamps_on_insert, propagate=True)
                event.listen(cls, "before_update", _set_timestamps_on_update, propagate=True)

    @classmethod
    async def all(cls) -> ModelCollection[Self]:
        # Narrows QueryMixin.all()'s list[Self] to the real runtime type so callers
        # get the relation-aware helpers (.load(), model_keys(), ...) without query().
        return cast("ModelCollection[Self]", await cls.query().all())

    @classmethod
    async def get(cls) -> ModelCollection[Self]:
        return cast("ModelCollection[Self]", await cls.query().get())

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
        if value is None:
            return value
        resolvers = type(self).__arvel_cast_resolvers__
        resolved = resolvers.get(name) if resolvers else None
        if resolved is None or resolved.read is None:
            return value
        return resolved.read(self, name, value)

    def __setattr__(self, name: str, value: Any) -> None:
        # Symmetric with __getattribute__: coerce on write so SA persists the cast
        # value, and so Model(field=raw) and m.field = raw both behave the same.
        if value is not None:
            # Mutators run first (transform), then casts (storage coercion).
            mutator_fn = type(self).__arvel_mutators__.get(name)
            if mutator_fn is not None:
                value = mutator_fn(self, value)

            resolvers = type(self).__arvel_cast_resolvers__
            resolved = resolvers.get(name) if resolvers else None
            if resolved is not None and resolved.write is not None:
                value = resolved.write(self, name, value)
        super().__setattr__(name, value)

    @overload
    def has_many(
        self,
        related: type[RelatedT],
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
    ) -> HasMany[RelatedT]: ...
    @overload
    def has_many(
        self,
        related: str,
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
    ) -> HasMany[Any]: ...
    def has_many(
        self,
        related: type[RelatedT] | str,
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
    ) -> HasMany[Any]:
        from arvel.database.orm.relations import HasMany

        related_cls = _resolve_related_model(type(self), related)
        lk = local_key or _pk_name(type(self))
        fk = foreign_key or f"{Str.snake(type(self).__name__)}_{lk}"
        owner_pk = getattr(self, lk)
        col = getattr(related_cls, fk)
        qb: HasMany[Any] = HasMany(
            related_cls, owner=self, fk_col=fk, owner_pk=owner_pk, local_key=lk
        )
        return qb.where(col == owner_pk)

    @overload
    def has_one(
        self,
        related: type[RelatedT],
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
    ) -> HasOne[RelatedT]: ...
    @overload
    def has_one(
        self,
        related: str,
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
    ) -> HasOne[Any]: ...
    def has_one(
        self,
        related: type[RelatedT] | str,
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
    ) -> HasOne[Any]:
        from arvel.database.orm.relations import HasOne

        related_cls = _resolve_related_model(type(self), related)
        lk = local_key or _pk_name(type(self))
        fk = foreign_key or f"{Str.snake(type(self).__name__)}_{lk}"
        owner_pk = getattr(self, lk)
        col = getattr(related_cls, fk)
        qb: HasOne[Any] = HasOne(
            related_cls, owner=self, fk_col=fk, owner_pk=owner_pk, local_key=lk
        )
        return qb.where(col == owner_pk)

    @overload
    def belongs_to(
        self,
        related: type[RelatedT],
        *,
        foreign_key: str | None = None,
        owner_key: str | None = None,
    ) -> BelongsTo[RelatedT]: ...
    @overload
    def belongs_to(
        self,
        related: str,
        *,
        foreign_key: str | None = None,
        owner_key: str | None = None,
    ) -> BelongsTo[Any]: ...
    def belongs_to(
        self,
        related: type[RelatedT] | str,
        *,
        foreign_key: str | None = None,
        owner_key: str | None = None,
    ) -> BelongsTo[Any]:
        from arvel.database.orm.relations import BelongsTo

        related_cls = _resolve_related_model(type(self), related)
        ok = owner_key or _pk_name(related_cls)
        fk = foreign_key or f"{Str.snake(related_cls.__name__)}_{ok}"
        fk_value = getattr(self, fk, None)
        pk_col = getattr(related_cls, ok)
        qb: BelongsTo[Any] = BelongsTo(
            related_cls, owner=self, fk_attr=fk, owner_key=ok, fk_present=fk_value is not None
        )
        if fk_value is not None:
            qb = qb.where(pk_col == fk_value)
        return qb

    def has_many_recursive(
        self,
        *,
        parent_key: str = "parent_id",
        local_key: str | None = None,
    ) -> Descendants[Self]:
        """All rows below this one in a self-referential (adjacency-list) tree.

        Walk the tree downward via ``parent_key``. ``await node.descendants().get()``
        is the flat subtree; ``.as_tree()`` is a TreeNode forest.
        """
        from arvel.database.orm.relations import Descendants

        lk = local_key or _pk_name(type(self))
        return Descendants(
            type(self),
            owner=self,
            owner_pk=getattr(self, lk),
            id_key=lk,
            parent_key=parent_key,
        )

    def belongs_to_recursive(
        self,
        *,
        parent_key: str = "parent_id",
        owner_key: str | None = None,
    ) -> Ancestors[Self]:
        """All rows above this one in a self-referential tree (walk upward)."""
        from arvel.database.orm.relations import Ancestors

        ok = owner_key or _pk_name(type(self))
        return Ancestors(
            type(self),
            owner=self,
            owner_pk=getattr(self, ok),
            id_key=ok,
            parent_key=parent_key,
        )

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

    @classmethod
    def on(cls, event: str, callback: Callable[[Any], Any]) -> None:
        """Register a single ``callback(instance)`` for one lifecycle ``event``.

        Lighter than a full observer class — the callback runs alongside any
        observers. Before-events (creating/updating/deleting/restoring) may
        return ``False`` to abort, same as observer hooks.
        """
        from arvel.database.events import register_callback

        register_callback(cls, event, callback)


def _timestamps_active(cls: type[Any]) -> bool:
    """True when ``cls`` wants timestamps and the current context hasn't muted them."""
    return bool(getattr(cls, "__timestamps__", True)) and not _suppress_timestamps.get()


def _set_timestamps_on_insert(_mapper: Mapper[Any], _conn: Any, target: Any) -> None:
    model = cast("Model", target)
    if not _timestamps_active(type(model)):
        return
    now = _datetime.now(UTC)
    created, updated = model.CREATED_AT, model.UPDATED_AT
    if created and getattr(model, created, None) is None:
        setattr(model, created, now)
    if updated and getattr(model, updated, None) is None:
        setattr(model, updated, now)


def _set_timestamps_on_update(_mapper: Mapper[Any], _conn: Any, target: Any) -> None:
    model = cast("Model", target)
    if not _timestamps_active(type(model)):
        return
    updated = model.UPDATED_AT
    if updated:
        setattr(model, updated, _datetime.now(UTC))


class Timestamps(MappedAsDataclass):
    """Mixin adding ``created_at`` and ``updated_at`` (auto-populated on save).

    Extends ``MappedAsDataclass`` so SQLAlchemy recognises it as a typed-
    dataclass mixin — required by SQLA 2.0 and will be enforced in 2.1.
    Both columns are ``init=False``; ``Model.__init_subclass__`` wires the
    mapper-event hooks that populate them (honoring ``__timestamps__`` and
    the ``CREATED_AT`` / ``UPDATED_AT`` constants).
    """

    created_at: Mapped[_datetime] = datetime(nullable=False, init=False, default=None)
    updated_at: Mapped[_datetime] = datetime(nullable=False, init=False, default=None)


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


class _UniqueIdProvider(Protocol):
    @classmethod
    def new_unique_id(cls) -> str: ...


def _set_unique_id_on_insert(_mapper: Any, _connection: Any, target: Any) -> None:
    """before_insert hook: fill an empty single-column PK from ``new_unique_id()``."""
    model = cast("Model", target)
    mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(type(model)))
    pk_cols = mapper.primary_key
    if len(pk_cols) != 1:
        return
    key = pk_cols[0].key
    if key is None or getattr(model, key, None) is not None:
        return
    provider = cast("type[_UniqueIdProvider]", type(model))
    setattr(model, key, provider.new_unique_id())


class HasUuids:
    """Mixin: auto-fill a string primary key with a UUID on insert.

    Declare the PK as a string column with ``init=False, default=None`` so it
    stays empty until the insert hook fills it.
    """

    @classmethod
    def new_unique_id(cls) -> str:
        import uuid

        return str(uuid.uuid4())

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        event.listen(cls, "before_insert", _set_unique_id_on_insert, propagate=True)


# Crockford base32 alphabet (no I, L, O, U) used by ULID encoding.
_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _new_ulid() -> str:
    """Generate a 26-char, lexicographically-sortable ULID (48-bit time + 80-bit random)."""
    import os
    import time

    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    chars = [""] * 26
    for i in range(25, -1, -1):
        chars[i] = _CROCKFORD32[value & 0x1F]
        value >>= 5
    return "".join(chars)


class HasUlids:
    """Mixin: auto-fill a string primary key with a sortable ULID on insert.

    Declare the PK as a string column with ``init=False, default=None``.
    """

    @classmethod
    def new_unique_id(cls) -> str:
        return _new_ulid()

    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        event.listen(cls, "before_insert", _set_unique_id_on_insert, propagate=True)


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
