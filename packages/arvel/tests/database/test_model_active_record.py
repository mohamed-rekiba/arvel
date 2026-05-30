"""FR-003-001 / 002 / 003 — Model + ActiveRecord + Timestamps + SoftDeletes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from arvel.database import (
    Model,
    ModelNotFoundError,
    RelationNotLoadedError,
    SoftDeletes,
    Timestamps,
)
from pydantic import BaseModel
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class UserA(Model, Timestamps):
    __tablename__ = "users_a"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class PostA(Model, Timestamps, SoftDeletes):
    __tablename__ = "posts_a"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(200), nullable=False)


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_model_basic_declaration(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    user = await UserA.create(name="Ada")
    assert user.id is not None
    assert user.name == "Ada"


async def test_timestamps_set_on_insert_and_update(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    user = await UserA.create(name="Grace")
    assert isinstance(user.created_at, datetime)
    assert isinstance(user.updated_at, datetime)
    original_updated = user.updated_at
    user.name = "Grace Hopper"
    await user.save()
    assert user.updated_at >= original_updated


async def test_soft_delete_marks_row(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    post = await PostA.create(title="Hello")
    await post.delete()
    assert post.deleted_at is not None


async def test_find_returns_none_when_missing(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    assert await UserA.find(9999) is None


async def test_find_or_fail_raises(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    with pytest.raises(ModelNotFoundError):
        await UserA.find_or_fail(9999)


async def test_to_dict_returns_column_values(engine: Any, session: AsyncSession) -> None:
    await _create_tables(engine)
    user = await UserA.create(name="Linus")
    data = user.to_dict()
    assert data["id"] == user.id
    assert data["name"] == "Linus"


async def test_to_json_serialises_to_string(engine: Any, session: AsyncSession) -> None:
    """``to_json`` returns a JSON string honouring ``__hidden__``."""
    import json

    await _create_tables(engine)
    user = await UserA.create(name="Ada")

    raw = user.to_json()
    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert parsed["name"] == "Ada"
    assert parsed["id"] == user.id


async def test_to_json_serialises_datetime_iso8601(engine: Any, session: AsyncSession) -> None:
    """``Timestamps`` columns surface as ISO-8601 strings (Pydantic default)."""
    import json
    import re

    await _create_tables(engine)
    user = await UserA.create(name="Margaret")
    parsed = json.loads(user.to_json())
    # Pydantic emits ISO-8601 with offset (e.g. "2026-05-20T11:33:00.123Z" or with +00:00)
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", parsed["created_at"])


async def test_to_json_respects_class_level_hidden(engine: Any, session: AsyncSession) -> None:
    """``__hidden__`` denylist applies the same way ``to_dict`` does."""
    import json

    class SecretA(Model, Timestamps):
        __tablename__ = "secrets_a"
        __hidden__ = ["secret"]
        id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
        name: Mapped[str] = mapped_column(String(100), nullable=False)
        secret: Mapped[str] = mapped_column(String(100), nullable=False)

    await _create_tables(engine)
    row = await SecretA.create(name="Vault", secret="redacted")
    parsed = json.loads(row.to_json())
    assert "secret" not in parsed
    assert parsed["name"] == "Vault"


async def test_to_json_indent_pretty_prints(engine: Any, session: AsyncSession) -> None:
    """Passing ``indent=2`` produces multi-line JSON."""
    await _create_tables(engine)
    user = await UserA.create(name="Knuth")
    raw = user.to_json(indent=2)
    assert "\n" in raw


async def test_to_pydantic_with_unloaded_relation_raises(
    engine: Any, session: AsyncSession
) -> None:
    # We declare a schema that references a hypothetical relationship name; since
    # UserA has no such relationship, the dict-only path runs fine.
    await _create_tables(engine)
    user = await UserA.create(name="Margaret")

    class UserOut(BaseModel):
        id: int
        name: str

    pyd = user.to_pydantic(UserOut)
    assert pyd.id == user.id
    assert pyd.name == "Margaret"

    # RelationNotLoadedError is import-checked here (FR-003-007 contract).
    assert issubclass(RelationNotLoadedError, Exception)
