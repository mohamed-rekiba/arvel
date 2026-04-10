"""Attribute casting — transparent type conversion on model get/set.

Define ``__casts__`` on any ArvelModel subclass to declare how column
values are transformed between Python and the database::

    class Secret(ArvelModel):
        __tablename__ = "secrets"
        __casts__ = {
            "options": "json",
            "secret": "encrypted",
            "role": MyEnum,
            "is_verified": "bool",
        }

Built-in cast types: ``json``, ``bool``, ``int``, ``float``, ``datetime``,
``encrypted``.  Pass an ``enum.Enum`` subclass to cast to/from enums.

Custom casts implement the ``Caster`` protocol (``get`` / ``set``).
"""

from __future__ import annotations

import enum
import json
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


class _Encrypter(Protocol):
    """Structural protocol for encryption/decryption services."""

    def encrypt(self, value: str) -> str: ...
    def decrypt(self, value: str) -> str: ...


@runtime_checkable
class Caster(Protocol):
    """Protocol for custom cast classes."""

    def get(self, value: Any, attr_name: str, model: object) -> Any:
        """Transform the database value into a Python value."""
        ...

    def set(self, value: Any, attr_name: str, model: object) -> Any:
        """Transform the Python value into a database value."""
        ...


# ──── Built-in casters ────


class JsonCaster:
    """Cast between Python dicts/lists and JSON strings."""

    def get(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)

    def set(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)


class BoolCaster:
    def get(self, value: Any, attr_name: str, model: object) -> bool | None:
        if value is None:
            return None
        return bool(value)

    def set(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        return bool(value)


class IntCaster:
    def get(self, value: Any, attr_name: str, model: object) -> int | None:
        if value is None:
            return None
        return int(value)

    def set(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        return int(value)


class FloatCaster:
    def get(self, value: Any, attr_name: str, model: object) -> float | None:
        if value is None:
            return None
        return float(value)

    def set(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        return float(value)


class DateTimeCaster:
    def get(self, value: Any, attr_name: str, model: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    def set(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return value


class EnumCaster:
    """Cast between enum members and their values."""

    def __init__(self, enum_cls: type[enum.Enum]) -> None:
        self._enum_cls = enum_cls

    def get(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        if isinstance(value, self._enum_cls):
            return value
        return self._enum_cls(value)

    def set(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        if isinstance(value, self._enum_cls):
            return value.value
        return value


class EncryptedCaster:
    """Cast via the framework's EncrypterContract.

    The encrypter is resolved lazily at first use to avoid circular imports.
    """

    def __init__(self, encrypter: _Encrypter | None = None) -> None:
        self._encrypter = encrypter

    def _get_encrypter(self) -> _Encrypter:
        if self._encrypter is not None:
            return self._encrypter
        msg = (
            "EncryptedCaster requires an encrypter instance. "
            "Pass it via __cast_encrypter__ on the model or configure the DI container."
        )
        raise RuntimeError(msg)

    def get(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        encrypter = self._resolve_encrypter(model)
        return encrypter.decrypt(value)

    def set(self, value: Any, attr_name: str, model: object) -> Any:
        if value is None:
            return None
        encrypter = self._resolve_encrypter(model)
        return encrypter.encrypt(value)

    def _resolve_encrypter(self, model: object) -> _Encrypter:
        model_encrypter = getattr(model, "__cast_encrypter__", None)
        if model_encrypter is not None:
            return model_encrypter  # type: ignore[return-value]
        if self._encrypter is not None:
            return self._encrypter
        return self._get_encrypter()


# ──── Registry ────

_BUILTIN_CASTS: dict[str, Caster] = {
    "json": JsonCaster(),
    "bool": BoolCaster(),
    "int": IntCaster(),
    "float": FloatCaster(),
    "datetime": DateTimeCaster(),
}


def resolve_caster(cast_spec: str | type | Caster) -> Caster:
    """Resolve a cast specification to a Caster instance."""
    if isinstance(cast_spec, Caster):
        return cast_spec

    if isinstance(cast_spec, str):
        if cast_spec == "encrypted":
            return EncryptedCaster()
        caster = _BUILTIN_CASTS.get(cast_spec)
        if caster is not None:
            return caster
        msg = f"Unknown cast type: {cast_spec!r}"
        raise ValueError(msg)

    if isinstance(cast_spec, type) and issubclass(cast_spec, enum.Enum):
        return EnumCaster(cast_spec)

    msg = f"Invalid cast specification: {cast_spec!r}"
    raise ValueError(msg)


def apply_get_casts(instance: object, casts: dict[str, Caster]) -> None:
    """Apply get-casts to all declared cast attributes on an instance."""
    for attr_name, caster in casts.items():
        raw = getattr(instance, attr_name, None)
        if raw is not None:
            cast_value = caster.get(raw, attr_name, instance)
            object.__setattr__(instance, attr_name, cast_value)


def apply_set_cast(instance: object, attr_name: str, value: Any, caster: Caster) -> Any:
    """Apply a set-cast to transform a value before storage."""
    return caster.set(value, attr_name, instance)
