"""arvel.search._JSONEncoder — the document JSON fallback for Meilisearch writes (Enum → value,
arvel Date → to_iso, anything with isoformat, else the stdlib TypeError)."""

from __future__ import annotations

import datetime
import enum
import json

import pytest

from arvel.search import _JSONEncoder  # pyright: ignore[reportPrivateUsage]


class _Color(enum.Enum):
    RED = "red"


class _ArvelDate:
    def to_iso(self) -> str:
        return "2026-07-05"


def test_encoder_handles_each_supported_shape() -> None:
    assert json.loads(json.dumps(_Color.RED, cls=_JSONEncoder)) == "red"
    assert json.loads(json.dumps(_ArvelDate(), cls=_JSONEncoder)) == "2026-07-05"
    stamp = datetime.datetime(2026, 7, 5, 12, 0, 0)
    assert json.dumps(stamp, cls=_JSONEncoder) == json.dumps(stamp.isoformat())


def test_encoder_raises_on_truly_unserializable() -> None:
    with pytest.raises(TypeError):
        json.dumps(object(), cls=_JSONEncoder)
