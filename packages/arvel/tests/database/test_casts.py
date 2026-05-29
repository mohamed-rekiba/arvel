"""FR-003-020..024 — Pydantic, Enum, and Encrypted casts."""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Any, cast

import pytest
from arvel.database import DecryptionError, EncryptedType, EnumType, Model, PydanticType
from pydantic import BaseModel
from sqlalchemy import Integer, create_engine
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


def _sqlite_dialect() -> Dialect:
    engine = create_engine("sqlite://")
    try:
        return engine.dialect
    finally:
        engine.dispose()


# ─── Pydantic type ────────────────────────────────────────────────────────────


class Preferences(BaseModel):
    theme: str = "light"
    notifications: bool = True


class UserPrefs(Model):
    __tablename__ = "user_prefs_c"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    prefs: Mapped[Preferences | None] = mapped_column(
        PydanticType(Preferences), nullable=True, default=None
    )


async def _setup(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_pydantic_type_round_trip(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    record = await UserPrefs.create(prefs=Preferences(theme="dark"))
    assert record.prefs is not None
    assert record.prefs.theme == "dark"
    fresh = await record.fresh()
    assert fresh is not None
    assert fresh.prefs is not None
    assert fresh.prefs.theme == "dark"
    assert fresh.prefs.notifications is True


async def test_pydantic_type_none_passes_through(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    record = await UserPrefs.create(prefs=None)
    assert record.prefs is None


def test_pydantic_type_decodes_json_string_result() -> None:
    dialect = _sqlite_dialect()
    cast_type = PydanticType(Preferences)

    assert cast_type.process_bind_param(None, dialect) is None
    assert cast_type.process_result_value(None, dialect) is None

    restored = cast_type.process_result_value('{"theme": "dark"}', dialect)
    assert restored is not None
    assert restored.theme == "dark"


# ─── Enum type ────────────────────────────────────────────────────────────────


class TaskStatus(enum.StrEnum):
    pending = "pending"
    done = "done"


class TaskC(Model):
    __tablename__ = "tasks_c"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    status: Mapped[TaskStatus] = mapped_column(
        EnumType(TaskStatus), nullable=False, default=TaskStatus.pending
    )


async def test_enum_type_round_trip(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    task = await TaskC.create(status=TaskStatus.done)
    fresh = await task.fresh()
    assert fresh is not None
    assert fresh.status is TaskStatus.done


def test_enum_type_accepts_raw_string_assignment() -> None:
    dialect = _sqlite_dialect()
    cast_type = EnumType(TaskStatus)
    bind = cast("Callable[[object | None, Dialect], object]", cast_type.process_bind_param)

    assert cast_type.process_bind_param(None, dialect) is None
    assert cast_type.process_result_value(None, dialect) is None
    assert bind("done", dialect) == "done"
    assert cast_type.process_result_value("done", dialect) is TaskStatus.done


# ─── Encrypted type ───────────────────────────────────────────────────────────


KEY = bytes.fromhex("00" * 32)
WRONG_KEY = bytes.fromhex("11" * 32)


class SecretCol(Model):
    __tablename__ = "secret_col_random"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    body: Mapped[str | None] = mapped_column(EncryptedType(KEY), nullable=True, default=None)


class SecretColDet(Model):
    __tablename__ = "secret_col_det"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    body: Mapped[str | None] = mapped_column(
        EncryptedType(KEY, deterministic=True), nullable=True, default=None
    )


async def test_encrypted_random_round_trip(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    row = await SecretCol.create(body="top secret")
    fresh = await row.fresh()
    assert fresh is not None
    assert fresh.body == "top secret"


async def test_encrypted_random_iv_changes_per_write(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    a = await SecretCol.create(body="same plaintext")
    b = await SecretCol.create(body="same plaintext")
    # Bypass the cast on read by querying the raw column value via the engine.
    async with engine.connect() as conn:
        rows = await conn.exec_driver_sql("SELECT body FROM secret_col_random ORDER BY id")
        a_raw, b_raw = [r[0] for r in rows.fetchall()]
    assert a_raw != b_raw  # randomized IV → different ciphertexts
    assert a.body == b.body == "same plaintext"


async def test_encrypted_deterministic_iv_matches_per_plaintext(
    engine: Any, session: AsyncSession
) -> None:
    await _setup(engine)
    await SecretColDet.create(body="lookup-me")
    await SecretColDet.create(body="lookup-me")
    async with engine.connect() as conn:
        rows = await conn.exec_driver_sql("SELECT body FROM secret_col_det")
        a_raw, b_raw = [r[0] for r in rows.fetchall()]
    assert a_raw == b_raw  # deterministic IV → identical ciphertext


async def test_encrypted_wrong_key_raises_decryption_error(
    engine: Any, session: AsyncSession
) -> None:
    await _setup(engine)
    await SecretCol.create(body="ciphertext")

    # Build a sibling model that maps to the same table but uses WRONG_KEY.
    class WrongKeyModel(Model):
        __tablename__ = "secret_col_random"
        __table_args__ = {"extend_existing": True}
        id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
        body: Mapped[str | None] = mapped_column(
            EncryptedType(WRONG_KEY), nullable=True, default=None
        )

    with pytest.raises(DecryptionError):
        await WrongKeyModel.first()


def test_encrypted_rejects_wrong_key_length() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        EncryptedType(b"too-short")


def test_encrypted_rejects_invalid_key_id() -> None:
    with pytest.raises(ValueError, match="1..32 ASCII bytes"):
        EncryptedType(KEY, key_id="")

    with pytest.raises(ValueError, match="1..32 ASCII bytes"):
        EncryptedType(KEY, key_id="x" * 33)


def test_encrypted_direct_decode_errors() -> None:
    dialect = _sqlite_dialect()
    cast_type = EncryptedType(KEY, key_id="v1", associated_data=b"secrets.body")
    other_key_id = EncryptedType(KEY, key_id="v2", associated_data=b"secrets.body")

    ciphertext = cast_type.process_bind_param("value", dialect)
    assert cast_type.process_result_value(ciphertext, dialect) == "value"

    with pytest.raises(DecryptionError, match="wire format version"):
        cast_type.process_result_value("AA==", dialect)

    with pytest.raises(DecryptionError, match="Key-id mismatch"):
        other_key_id.process_result_value(ciphertext, dialect)

    tampered = ciphertext[:-2] + "AA"
    with pytest.raises(DecryptionError, match="Failed to decrypt"):
        cast_type.process_result_value(tampered, dialect)
