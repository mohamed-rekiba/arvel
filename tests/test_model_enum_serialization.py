"""to_dict()/to_json() serialize an enum-cast column to its scalar value — not the raw enum
member. Regression: to_dict left ``<Role.ADMIN: 'admin'>`` unserialized while dates were ISO'd."""

from __future__ import annotations

import enum
from typing import ClassVar

from arvel.database import Model


class Role(enum.Enum):
    ADMIN = "admin"


class Status(enum.StrEnum):
    OPEN = "open"


class Account(Model):
    __fields__: ClassVar = {"name": str, "role": str, "status": str}
    __casts__: ClassVar = {"role": Role, "status": Status}


def _account() -> Account:
    acc = Account()
    object.__setattr__(acc, "_attributes", {"name": "Ada", "role": "admin", "status": "open"})
    return acc


def test_to_dict_serializes_enum_cast_to_its_value() -> None:
    acc = _account()
    # the accessor still returns the real enum member…
    assert acc.role is Role.ADMIN
    # …but to_dict yields the scalar value, JSON-native
    data = acc.to_dict()
    assert data["role"] == "admin" and isinstance(data["role"], str)
    assert data["status"] == "open" and isinstance(data["status"], str)


def test_to_json_serializes_enum_cast() -> None:
    out = _account().to_json()
    assert '"role": "admin"' in out
    assert '"status": "open"' in out


# --- to_serializable is deep + complete (to_dict must match to_json) ---------
def test_to_serializable_covers_all_types_json_native() -> None:
    import datetime
    import json
    import uuid

    from arvel.database.model_casts import to_serializable
    from arvel.dates import Date
    from arvel.support import Collection

    d = Date.from_py(datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC))
    cases = [
        Collection([d]),  # collection cast
        [d],  # array cast
        {"at": d},  # json cast, nested Date
        [{"a": d}, {"b": [d]}],  # deeply nested
        datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),  # stdlib datetime
        uuid.uuid4(),  # UUID column
        Role.ADMIN,  # enum
    ]
    for value in cases:
        out = to_serializable(value)
        json.dumps(out)  # every result is JSON-native (raises otherwise)
    # the Date inside a container is serialized, not left raw
    assert to_serializable(Collection([d])) == [d.to_iso()]
    assert to_serializable({"at": d}) == {"at": d.to_iso()}
