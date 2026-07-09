"""arvel.database.model_casts — ``HasCasts``: attribute accessors/mutators + the cast registry. Grounded in knowledge/port/07-orm-active-record.md.

Cast keys: ``datetime``/``bool``/``int``/``json``/``array``/``collection``/``object``/
``decimal:<scale>``/``hashed``/``encrypted``/``encrypted:array``/``encrypted:json``/
``stringable``, a native ``enum.Enum`` subclass, or a custom object exposing ``get``/``set``
(the ``Cast`` protocol). ``immutable_datetime`` is deliberately **not** added — arvel's
``datetime`` cast already returns the immutable, whenever-based ``Date`` (a built-in
divergence from, which needs a separate cast because its default is mutable Carbon).
"""

from __future__ import annotations

import enum
import json
from typing import Any, ClassVar, cast

#: cast keys whose column is a plain TEXT (the cast owns (de)serialization; a native JSON/DECIMAL
#: column's asymmetric read/write processors would double-encode on every write — see model.py).
TEXT_CASTS = frozenset(
    {"json", "array", "collection", "object", "encrypted:array", "encrypted:json"}
)


def uses_text_column(cast: Any) -> bool:
    """Whether ``cast`` (a ``__casts__`` value) is stored as a plain TEXT column."""
    return isinstance(cast, str) and (cast in TEXT_CASTS or cast.startswith("decimal:"))


def json_default(value: Any) -> Any:
    """JSON fallback for ``to_json``/the json-family casts — Date/Decimal/Enum and anything with
    ``isoformat``/``to_iso``."""
    if isinstance(value, enum.Enum):
        return value.value
    if hasattr(value, "to_iso"):  # arvel Date
        return value.to_iso()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def to_serializable(value: Any) -> Any:
    """Unwrap a cast-get result to a JSON-native value for ``to_dict``:
    ``collection`` -> list, ``object`` -> dict, ``stringable`` -> str, ``Decimal`` -> str,
    a datetime-cast ``Date`` -> ISO string (the same serializer ``json_default`` falls back to,
    so ``to_dict``/``to_json`` agree and ``json_default`` never fires for this field). Read-path
    only; ``_cast_set`` already unwraps for the write path."""
    from decimal import Decimal
    from types import SimpleNamespace

    from arvel.dates import Date
    from arvel.support import Collection, Stringable

    if isinstance(value, Date):
        return value.to_iso()
    if isinstance(value, Collection):
        return cast("list[Any]", value.to_list())
    if isinstance(value, SimpleNamespace):
        return vars(value)
    if isinstance(value, (Stringable, Decimal)):
        return str(value)
    return value


def _to_db_datetime(value: Any) -> Any:
    """Normalize a Date / stdlib datetime / ISO string to a **UTC-aware** stdlib ``datetime`` for
    storage. UTC is the on-disk timezone so the round-trip is instant-faithful on every dialect:
    Postgres ``timestamptz`` keeps the instant regardless, and SQLite (which drops the offset and
    reads back a naive value) then stores a UTC wall-clock that:func:`_from_db_datetime` reads as
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
    dropped the offset) — it was stored as a UTC wall-clock (see:func:`_to_db_datetime`), so attach
    UTC. The Builder's RAW read path (``select_raw``) skips result processors entirely, so on
    SQLite the very same column arrives as its stored **string** (``'2026-07-02 21:41:10.506842'``)
    — parse it (stdlib ``fromisoformat`` accepts the space separator) and apply the same naive-
    means-UTC rule. Anything unparseable passes through for:meth:`Date.from_py` to reject."""
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


def now_utc() -> Any:
    """The current instant as a UTC-aware stdlib ``datetime`` — bound into real ``DateTime``
    timestamp/soft-delete columns (the DB driver needs a datetime, not an ISO string)."""
    from arvel.dates import Date

    return _to_db_datetime(Date.now())


class HasCasts:
    """Attribute accessors/mutators (``Attribute``-returning methods) + the ``__casts__``
    registry — ``_cast_get``/``_cast_set`` are consulted by ``Model.__getattr__``/``__setattr__``
    and by ``fill``/``_hydrate``.

    The ``__casts__``/``__fields__``/``_attributes`` etc. attribute declarations below are a
    mixin type stub only — the real ClassVar defaults + instance state live on ``Model`` (the
    concrete class always precedes this mixin in the MRO, so ``Model``'s own definitions are what
    actually run; this just gives the type checker the shape ``HasCasts`` depends on)."""

    __casts__: ClassVar[dict[str, Any]]
    __timestamps__: ClassVar[bool]
    __fields__: ClassVar[dict[str, Any]]
    __attributes_meta__: ClassVar[dict[str, Any]]
    _attributes: dict[str, Any]
    _accessor_cache: dict[str, Any]

    @classmethod
    def _uses_soft_deletes(cls) -> bool:  # provided by Model core
        raise NotImplementedError

    # --- casts -----------------------------------------------------------------
    def _accessor(self, key: str) -> Any:
        """The Attribute for ``key`` if a model accessor/mutator method defines one."""
        method = type(self).__attributes_meta__.get(key)
        return method(self) if method is not None else None

    def _effective_cast(self, key: str) -> Any:
        """The cast for ``key`` — an explicit ``__casts__`` entry, an implicit ``datetime`` for the
        timestamp/soft-delete columns (casts created_at/updated_at/deleted_at to Carbon by
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
        if cast in ("json", "array"):
            return json.loads(value) if isinstance(value, str) else value
        if cast == "collection":
            from arvel.support import Collection

            data = json.loads(value) if isinstance(value, str) else value
            return Collection(data)
        if cast == "object":
            from types import SimpleNamespace

            data = json.loads(value) if isinstance(value, str) else value
            return SimpleNamespace(**data) if isinstance(data, dict) else data
        if cast == "stringable":
            from arvel.support import Stringable

            return value if isinstance(value, Stringable) else Stringable(value)
        if isinstance(cast, str) and cast.startswith("decimal:"):
            return _to_decimal(value, cast)
        if cast == "encrypted":
            return self._crypt().decrypt_string(value)
        if cast in ("encrypted:array", "encrypted:json"):
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
        if cast in ("json", "array") and not isinstance(value, str):
            # json_default handles Date/datetime/Decimal/Enum nested in the value (e.g. an activity
            # log snapshot of a model whose attributes include timestamps) — plain json.dumps can't.
            return json.dumps(value, default=json_default)
        if cast == "collection" and not isinstance(value, str):
            return json.dumps(_as_list(value), default=json_default)
        if cast == "object" and not isinstance(value, str):
            from types import SimpleNamespace

            data = vars(value) if isinstance(value, SimpleNamespace) else value
            return json.dumps(data, default=json_default)
        if cast == "stringable":
            from arvel.support import Stringable

            return str(value) if isinstance(value, Stringable) else value
        if isinstance(cast, str) and cast.startswith("decimal:") and value is not None:
            return _from_decimal(value, cast)
        if cast == "datetime" and value is not None:
            # store a UTC-aware stdlib datetime so SQLAlchemy binds it to the real DateTime column
            # (accepts a Date, an ISO string, or a datetime) and the round-trip stays instant-faithful
            return _to_db_datetime(value)
        if cast == "hashed" and value is not None:
            return self._hash().make(value)
        if cast == "encrypted" and value is not None:
            return self._crypt().encrypt_string(value)
        if cast in ("encrypted:array", "encrypted:json") and value is not None:
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


def _as_list(value: Any) -> list[Any]:
    """``value`` as a plain list for the ``collection`` cast's write side — unwraps an
    ``arvel.support.Collection`` via ``to_list()``, else lists any other iterable."""
    to_list = getattr(value, "to_list", None)
    if to_list is None:
        return list(value)
    items: Any = to_list()
    return list(items)


def _decimal_scale(cast: str) -> int:
    return int(cast.split(":", 1)[1])


def _to_decimal(value: Any, cast: str) -> Any:
    """``decimal:<scale>`` on read — a quantized ``decimal.Decimal`` (arvel's idiomatic divergence:
    the ``decimal`` cast returns a formatted string, arvel returns a real ``Decimal``)."""
    from decimal import Decimal

    quantum = Decimal(1).scaleb(-_decimal_scale(cast))
    return (value if isinstance(value, Decimal) else Decimal(str(value))).quantize(quantum)


def _from_decimal(value: Any, cast: str) -> str:
    """``decimal:<scale>`` on write — quantized, stored as its exact string form (a plain TEXT
    column keeps the precision dialect-independent — see:data:`TEXT_CASTS`)."""
    from decimal import Decimal

    quantum = Decimal(1).scaleb(-_decimal_scale(cast))
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    return str(dec.quantize(quantum))


__all__ = ["TEXT_CASTS", "HasCasts", "uses_text_column"]
