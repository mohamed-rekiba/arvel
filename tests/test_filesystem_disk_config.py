"""Filesystem (doc 16) — disk configs flow from config("filesystems.disks.*") into the fsspec call."""

from __future__ import annotations

from typing import Any

import arvel.filesystem as fsmod
from arvel.filesystem import FilesystemManager
from arvel.kernel import Application, set_application


class _RecordingFsspec:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def filesystem(self, protocol: str, **kwargs: Any) -> object:
        self.calls.append((protocol, kwargs))
        return object()


def _app_with_disks(**disks: dict[str, Any]) -> Application:
    app = Application()
    app.make("config").set("filesystems", {"disks": disks})
    set_application(app)  # config() is the single source of truth (DR-0016)
    return app


def test_connection_string_path(monkeypatch: Any) -> None:
    rec = _RecordingFsspec()
    monkeypatch.setattr(fsmod, "_fsspec", lambda: rec)
    _app_with_disks(azure={"connection_string": "Endpoint=...;", "container": "media"})
    try:
        FilesystemManager().disk("azure")
        proto, kwargs = rec.calls[-1]
        assert proto == "az"
        assert kwargs == {"connection_string": "Endpoint=...;"}  # not account_name/key
    finally:
        set_application(None)


def test_account_creds_path(monkeypatch: Any) -> None:
    rec = _RecordingFsspec()
    monkeypatch.setattr(fsmod, "_fsspec", lambda: rec)
    _app_with_disks(azure={"account_name": "acct", "account_key": "k"})
    try:
        FilesystemManager().disk("azure")
        proto, kwargs = rec.calls[-1]
        assert proto == "az"
        assert kwargs == {"account_name": "acct", "account_key": "k"}
    finally:
        set_application(None)


def test_gcs_passes_token_and_bucket(monkeypatch: Any) -> None:
    rec = _RecordingFsspec()
    monkeypatch.setattr(fsmod, "_fsspec", lambda: rec)
    _app_with_disks(gcs={"token": "anon", "bucket": "media"})
    try:
        disk = FilesystemManager().disk("gcs")
        proto, kwargs = rec.calls[-1]
        assert proto == "gcs"
        assert kwargs == {"token": "anon"}
        assert disk._root == "media"  # bucket becomes the disk root
    finally:
        set_application(None)


def test_s3_passes_endpoint_url_when_set(monkeypatch: Any) -> None:
    rec = _RecordingFsspec()
    monkeypatch.setattr(fsmod, "_fsspec", lambda: rec)
    _app_with_disks(
        s3={"key": "k", "secret": "s", "endpoint_url": "http://rustfs:9000", "bucket": "b"}
    )
    try:
        FilesystemManager().disk("s3")
        proto, kwargs = rec.calls[-1]
        assert proto == "s3"
        assert kwargs["client_kwargs"] == {"endpoint_url": "http://rustfs:9000"}  # path-style
    finally:
        set_application(None)
