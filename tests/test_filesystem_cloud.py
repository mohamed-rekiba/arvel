"""GCS/Azure disk drivers (wiring verified via a fake fsspec)."""

from __future__ import annotations

from typing import Any

import pytest

import arvel.filesystem as fsmod
from arvel.filesystem import Filesystem, FilesystemManager


class FakeFsspec:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def filesystem(self, protocol: str, **kwargs: Any) -> object:
        self._store["protocol"] = protocol
        self._store["kwargs"] = kwargs
        return object()


def test_gcs_driver_uses_gcs_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}
    monkeypatch.setattr(fsmod, "_fsspec", lambda: FakeFsspec(recorded))
    disk = FilesystemManager().create_gcs_driver()
    assert isinstance(disk, Filesystem)
    assert recorded["protocol"] == "gcs"


def test_azure_driver_uses_az_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}
    monkeypatch.setattr(fsmod, "_fsspec", lambda: FakeFsspec(recorded))
    disk = FilesystemManager().create_azure_driver()
    assert isinstance(disk, Filesystem)
    assert recorded["protocol"] == "az"


def test_drivers_resolve_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}
    monkeypatch.setattr(fsmod, "_fsspec", lambda: FakeFsspec(recorded))
    # Manager.driver("gcs") dispatches to create_gcs_driver
    assert isinstance(FilesystemManager().driver("gcs"), Filesystem)
    assert recorded["protocol"] == "gcs"
