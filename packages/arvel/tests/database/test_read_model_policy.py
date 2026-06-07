"""``ReadModelPolicy.guard()`` — runtime guard against direct write-model queries."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database.exceptions import ReadOnlyModelError
from arvel.database.policy import (
    ImmutableReadModelError,
    ReadModelPolicy,
    ReadModelPolicyViolationError,
)


# Use real class definitions so `__name__` matches the assertion target.
class PublishedThing:
    pass


class _ThingBase:
    """Stand-in for an ORM model exposing the ``add_global_scope`` API.

    Mirrors ``arvel.database.Model``'s scope API so the guard can be tested
    without a live SQLAlchemy session.
    """

    __arvel_global_scopes__: dict[str, Any] = {}

    @classmethod
    def add_global_scope(cls, name: str, scope: Any) -> None:
        if "__arvel_global_scopes__" not in cls.__dict__:
            cls.__arvel_global_scopes__ = {}
        cls.__arvel_global_scopes__[name] = scope

    @classmethod
    def fire_scopes(cls) -> None:
        # What QueryBuilder._apply_global_scopes() effectively does.
        for fn in list(cls.__dict__.get("__arvel_global_scopes__", {}).values()):
            fn(None)


def _fresh_write_model() -> type[_ThingBase]:
    # Subclass per test so ``__arvel_global_scopes__`` starts empty.
    return type("Thing", (_ThingBase,), {"__arvel_global_scopes__": {}})


def test_guard_blocks_direct_query_on_write_model() -> None:
    write = _fresh_write_model()
    policy = ReadModelPolicy(read_model=PublishedThing, write_model=write)

    with policy.guard(), pytest.raises(ReadModelPolicyViolationError) as exc:
        write.fire_scopes()

    msg = str(exc.value)
    assert "PublishedThing" in msg
    assert "Thing" in msg
    assert exc.value.write_model_name == "Thing"
    assert exc.value.read_model_name == "PublishedThing"


def test_guard_removes_scope_on_exit() -> None:
    write = _fresh_write_model()
    policy = ReadModelPolicy(read_model=PublishedThing, write_model=write)

    assert write.__dict__["__arvel_global_scopes__"] == {}
    with policy.guard():
        assert len(write.__dict__["__arvel_global_scopes__"]) == 1

    assert write.__dict__["__arvel_global_scopes__"] == {}


def test_multiple_policies_isolate_their_scopes() -> None:
    write = _fresh_write_model()
    policy_a = ReadModelPolicy(read_model=PublishedThing, write_model=write)
    policy_b = ReadModelPolicy(read_model=PublishedThing, write_model=write)

    with policy_a.guard(), policy_b.guard():
        # Both scopes registered under distinct keys (id(self)).
        assert len(write.__dict__["__arvel_global_scopes__"]) == 2

    assert write.__dict__["__arvel_global_scopes__"] == {}


def test_immutable_read_model_error_is_alias_for_read_only_model_error() -> None:
    # Re-export contract: callers can import either spelling.
    assert ImmutableReadModelError is ReadOnlyModelError
