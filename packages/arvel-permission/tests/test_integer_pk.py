"""Tests for integer PK support in arvel-permission — FR-032-08 / AC-19..20.

Tests are written RED — make_roles_relationship / make_permissions_relationship
do not exist yet in arvel_permission.traits.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
)
from sqlalchemy import (
    Integer as _Integer,
)
from sqlalchemy import (
    MetaData as _MetaData,
)
from sqlalchemy import (
    String as _String,
)
from sqlalchemy import (
    Table as _Table,
)

# ─── Fake models for factory tests ───────────────────────────────────────────

_fake_meta = _MetaData()


class _FakeIntModel:
    """Simulates a model with integer PK — has a real __table__ for factory tests."""

    __tablename__ = "fake_int_models"
    __table__ = _Table(
        "fake_int_models",
        _fake_meta,
        Column("id", _Integer, primary_key=True),
    )


class _FakeStrModel:
    """Simulates a model with string/UUID PK."""

    __tablename__ = "fake_str_models"
    __table__ = _Table(
        "fake_str_models",
        _fake_meta,
        Column("id", _String(36), primary_key=True),
    )


# ─── AC-19: importable factory functions ─────────────────────────────────────


def test_factory_functions_importable() -> None:
    from arvel_permission.traits import (
        make_permissions_relationship,
        make_roles_relationship,
    )

    assert callable(make_permissions_relationship)
    assert callable(make_roles_relationship)


# ─── AC-19: integer PK model can use factory without cast/type-ignore ─────────


def test_integer_pk_relationship_factory_exists() -> None:
    """make_roles_relationship must return a SQLAlchemy relationship descriptor."""
    from arvel_permission.traits import make_roles_relationship

    rel = make_roles_relationship(lambda: _FakeIntModel, model_type="FakeIntModel")
    assert rel is not None


def test_permissions_relationship_factory_exists() -> None:
    from arvel_permission.traits import make_permissions_relationship

    rel = make_permissions_relationship(lambda: _FakeIntModel, model_type="FakeIntModel")
    assert rel is not None


# ─── AC-20: string/UUID PK model still works (regression) ────────────────────


def test_string_pk_relationship_factory_works() -> None:
    from arvel_permission.traits import make_roles_relationship

    rel = make_roles_relationship(lambda: _FakeStrModel, model_type="FakeStrModel")
    assert rel is not None


# ─── No new type: ignore needed in consuming model ───────────────────────────
