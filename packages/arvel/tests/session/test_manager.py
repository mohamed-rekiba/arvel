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
    manager = SessionManager(SessionConfig(driver=SessionDriver.FILE, files_path=str(path)))

    first = manager.store()
    second = manager.store("file")

    assert first is second
    assert isinstance(first, FileSessionStore)


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
    manager = SessionManager(SessionConfig(driver=SessionDriver.FILE, files_path=str(path)))

    session = await manager.create_session()
    session.put("user_id", 123)
    await manager.save_session(session)

    restored = await manager.create_session(session.get_id())
    assert restored.get("user_id") == 123


async def test_save_session_destroys_rotated_id(tmp_path: Path) -> None:
    # regenerate() queues the old id; save_session must drop that record so a
    # pre-login session can't outlive the rotation.
    path = tmp_path / "sessions"
    manager = SessionManager(SessionConfig(driver=SessionDriver.FILE, files_path=str(path)))

    session = await manager.create_session()
    session.put("user_id", 123)
    await manager.save_session(session)
    old_id = session.get_id()

    session.regenerate()
    await manager.save_session(session)

    assert await manager.store().read(old_id) == {}
