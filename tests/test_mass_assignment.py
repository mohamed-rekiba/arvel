"""Mass-assignment guarding (doc 07) — Laravel parity. A *totally-guarded* model (the default
``__guarded__ == ['*']`` with no ``__fillable__``) raises ``MassAssignmentException`` when you
mass-assign attributes, instead of silently discarding them into an empty row. Models that declare
``__fillable__`` keep silently discarding non-fillable keys (Laravel's behavior for partially-guarded
models); a fully-unguarded model (``__guarded__ == []``) fills everything."""

from __future__ import annotations

from typing import ClassVar

import pytest

from arvel.database import MassAssignmentException, Model


class _Guarded(Model):
    __table_name__ = "guarded_things"  # totally guarded: default __guarded__ == ['*'], no fillable


class _Fillable(Model):
    __table_name__ = "fillable_things"
    __fillable__: ClassVar[list[str]] = ["name"]


class _Unguarded(Model):
    __table_name__ = "unguarded_things"
    __guarded__: ClassVar[list[str]] = []


def test_totally_guarded_fill_raises_listing_the_attributes() -> None:
    m = _Guarded()
    with pytest.raises(MassAssignmentException) as ei:
        m.fill({"name": "x", "evil_admin": True})
    msg = str(ei.value)
    assert "name" in msg and "evil_admin" in msg
    assert "_Guarded" in msg  # names the model, like Laravel


def test_fillable_model_silently_discards_non_fillable() -> None:
    # partially-guarded (fillable declared) keeps Laravel's silent-discard — only the extra is dropped
    m = _Fillable()
    m.fill({"name": "ok", "sneaky": True})
    assert m._attributes == {"name": "ok"}  # no raise; sneaky dropped


def test_unguarded_model_fills_everything() -> None:
    m = _Unguarded()
    m.fill({"name": "ok", "anything": 1})
    assert m._attributes == {"name": "ok", "anything": 1}


def test_totally_guarded_with_no_attributes_does_not_raise() -> None:
    # nothing to discard -> no exception (mirrors Laravel: only raises when attrs are actually dropped)
    assert _Guarded().fill({})._attributes == {}


async def test_create_on_totally_guarded_raises_before_touching_the_db() -> None:
    # create() fills before save(), so the guard fires without any DB bound
    with pytest.raises(MassAssignmentException):
        await _Guarded.create(name="x")
