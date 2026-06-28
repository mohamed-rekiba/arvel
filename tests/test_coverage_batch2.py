"""Coverage — Str predicates, mail smtp/config, queue manager default, filesystem drivers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import arvel.filesystem as fsmod
from arvel.filesystem import Filesystem, FilesystemManager
from arvel.mail import MailManager
from arvel.support import Str


# --- Str predicates -----------------------------------------------------------
def test_str_predicates_and_slicing() -> None:
    assert Str.contains("hello", "ell")
    assert Str.starts_with("hello", "he")
    assert Str.ends_with("hello", "lo")
    assert Str.limit("hello world", 5) == "hello..."
    assert Str.after("a.b.c", ".") == "b.c"
    assert Str.before("a.b.c", ".") == "a"


# --- mail ---------------------------------------------------------------------
def test_smtp_transport_builds_real_client() -> None:
    import aiosmtplib

    transport = MailManager().driver("smtp")
    assert isinstance(transport.client, aiosmtplib.SMTP)


def test_mail_default_driver_and_config_from_app() -> None:
    from arvel.kernel import Application, set_application
    from arvel.mail import MailSettings

    app = Application()
    app.make("config").set("mail", {"default": "smtp", "smtp": {"host": "mail.test", "port": 25}})
    set_application(app)  # config() is the single source of truth (DR-0016)
    try:
        assert MailManager(app).default_driver() == "smtp"
        assert MailSettings().smtp.host == "mail.test"
    finally:
        set_application(None)


# --- queue manager default ----------------------------------------------------
def test_queue_manager_default_without_app() -> None:
    import arvel.queue as queue_mod
    from arvel.kernel import set_application
    from arvel.queue import QueueManager

    set_application(None)
    assert isinstance(queue_mod._queue_manager(), QueueManager)


# --- filesystem ---------------------------------------------------------------
class _FakeFsspec:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def filesystem(self, protocol: str, **kwargs: Any) -> object:
        self._store["protocol"] = protocol
        return object()


def test_s3_driver_uses_s3_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}
    monkeypatch.setattr(fsmod, "_fsspec", lambda: _FakeFsspec(recorded))
    disk = FilesystemManager().create_s3_driver()
    assert isinstance(disk, Filesystem)
    assert recorded["protocol"] == "s3"


async def test_put_creates_nested_parents(tmp_path: Path) -> None:
    import fsspec

    fs = Filesystem(fsspec.filesystem("file"), root=str(tmp_path))
    await fs.put("a/b/c.txt", "hi")  # nested path -> makedirs branch
    assert await fs.exists("a/b/c.txt")
    assert await fs.get("a/b/c.txt") == b"hi"
    await fs.delete("a/b/c.txt")
    assert not await fs.exists("a/b/c.txt")
