"""SessionManager driver and persistence coverage."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.config.session_config import SessionConfig
from arvel.session import SessionManager
from arvel.session.stores.cookie import CookieStore
from arvel.session.stores.file import FileSessionStore
from pydantic import SecretStr


def test_session_manager_caches_store_instances(tmp_path: Path) -> None:
    path = tmp_path / "sessions"
    manager = SessionManager(SessionConfig(driver="file", files_path=str(path)))

    first = manager.store()
    second = manager.store("file")

    assert first is second
    assert isinstance(first, FileSessionStore)


def test_session_manager_creates_cookie_store() -> None:
    manager = SessionManager(SessionConfig(driver="cookie", secret_key=SecretStr("0" * 32)))
    assert isinstance(manager.store(), CookieStore)


def test_session_manager_rejects_unknown_driver() -> None:
    manager = SessionManager(SessionConfig(driver="unknown"))

    with pytest.raises(ValueError, match="Unsupported session driver"):
        manager.store()


async def test_session_manager_create_and_save_session(tmp_path: Path) -> None:
    path = tmp_path / "sessions"
    manager = SessionManager(SessionConfig(driver="file", files_path=str(path)))

    session = await manager.create_session()
    session.put("user_id", 123)
    await manager.save_session(session)

    restored = await manager.create_session(session.get_id())
    assert restored.get("user_id") == 123
