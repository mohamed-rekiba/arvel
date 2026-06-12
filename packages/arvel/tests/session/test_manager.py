"""SessionManager driver and persistence coverage."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.config.session_config import SessionConfig, SessionDriver
from arvel.session import SessionManager
from arvel.session.stores.cookie import CookieStore
from arvel.session.stores.file import FileSessionStore
from pydantic import SecretStr, ValidationError


def test_session_manager_caches_store_instances(tmp_path: Path) -> None:
    path = tmp_path / "sessions"
    manager = SessionManager(
        SessionConfig(
            driver=SessionDriver.FILE, files_path=str(path), secret_key=SecretStr("0" * 32)
        )
    )

    first = manager.store()
    second = manager.store("file")

    assert first is second
    assert isinstance(first, FileSessionStore)


@pytest.mark.asyncio
async def test_session_manager_shutdown_drains_owned_connections() -> None:
    # The db/redis drivers create a pool the manager owns; shutdown() must drain
    # every registered closer and clear caches so nothing leaks past teardown.
    manager = SessionManager(
        SessionConfig(driver=SessionDriver.COOKIE, secret_key=SecretStr("0" * 32))
    )
    closed = {"n": 0}

    async def _close() -> None:
        closed["n"] += 1

    manager.register_closer(_close)
    manager.store()

    await manager.shutdown()

    # closer was called exactly once; a second shutdown() must be safe too.
    assert closed["n"] == 1
    await manager.shutdown()
    assert closed["n"] == 1


def test_session_manager_creates_cookie_store() -> None:
    manager = SessionManager(
        SessionConfig(driver=SessionDriver.COOKIE, secret_key=SecretStr("0" * 32))
    )
    assert isinstance(manager.store(), CookieStore)


def test_cookie_driver_requires_secret_key() -> None:
    # Empty SESSION_SECRET_KEY would derive crypto keys from empty material —
    # fail fast instead of silently shipping a weak cookie store.
    manager = SessionManager(SessionConfig(driver=SessionDriver.COOKIE, secret_key=SecretStr("")))
    with pytest.raises(ValueError, match="SESSION_SECRET_KEY is required"):
        manager.store()


def test_session_manager_creates_array_store_for_tests() -> None:
    from arvel.session.stores.array import ArraySessionStore

    manager = SessionManager(SessionConfig(driver=SessionDriver.ARRAY))
    assert isinstance(manager.store(), ArraySessionStore)


def test_config_rejects_unknown_driver() -> None:
    # Invalid drivers now fail fast at config validation, not at store() time.
    with pytest.raises(ValidationError):
        SessionConfig.model_validate({"driver": "unknown"})


def test_store_with_unknown_name_raises() -> None:
    manager = SessionManager(SessionConfig(driver=SessionDriver.ARRAY))
    with pytest.raises(ValueError, match="not a valid SessionDriver"):
        manager.store("unknown")


async def test_session_manager_create_and_save_session(tmp_path: Path) -> None:
    path = tmp_path / "sessions"
    manager = SessionManager(
        SessionConfig(
            driver=SessionDriver.FILE, files_path=str(path), secret_key=SecretStr("0" * 32)
        )
    )

    session = await manager.create_session()
    session.put("user_id", 123)
    await manager.save_session(session)

    restored = await manager.create_session(session.get_id())
    assert restored.get("user_id") == 123


async def test_file_store_encrypts_payload_at_rest(tmp_path: Path) -> None:
    # SESSION_ENCRYPT must hold for server-side stores too, not just cookies.
    path = tmp_path / "sessions"
    manager = SessionManager(
        SessionConfig(
            driver=SessionDriver.FILE, files_path=str(path), secret_key=SecretStr("0" * 32)
        )
    )

    session = await manager.create_session()
    session.put("secret", "top-secret-value")
    await manager.save_session(session)

    on_disk = b"".join(f.read_bytes() for f in path.glob("*.session"))
    assert b"top-secret-value" not in on_disk
    assert (await manager.create_session(session.get_id())).get("secret") == "top-secret-value"


async def test_file_store_plaintext_when_encrypt_disabled(tmp_path: Path) -> None:
    path = tmp_path / "sessions"
    manager = SessionManager(
        SessionConfig(driver=SessionDriver.FILE, files_path=str(path), encrypt=False)
    )

    session = await manager.create_session()
    session.put("user_id", 123)
    await manager.save_session(session)

    on_disk = b"".join(f.read_bytes() for f in path.glob("*.session"))
    assert b"user_id" in on_disk


def test_file_driver_requires_secret_when_encrypt_enabled(tmp_path: Path) -> None:
    # The documented contract: SESSION_SECRET_KEY is required whenever encryption
    # is on, for every server-side driver — not silently downgraded to plaintext.
    manager = SessionManager(
        SessionConfig(driver=SessionDriver.FILE, files_path=str(tmp_path / "s"))
    )
    with pytest.raises(ValueError, match="SESSION_SECRET_KEY is required"):
        manager.store()


async def test_save_session_destroys_rotated_id(tmp_path: Path) -> None:
    # regenerate() queues the old id; save_session must drop that record so a
    # pre-login session can't outlive the rotation.
    path = tmp_path / "sessions"
    manager = SessionManager(
        SessionConfig(
            driver=SessionDriver.FILE, files_path=str(path), secret_key=SecretStr("0" * 32)
        )
    )

    session = await manager.create_session()
    session.put("user_id", 123)
    await manager.save_session(session)
    old_id = session.get_id()

    session.regenerate()
    await manager.save_session(session)

    assert await manager.store().read(old_id) == {}
