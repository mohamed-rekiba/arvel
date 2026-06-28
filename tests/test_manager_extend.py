"""Managers (doc 16) — verify the extend() custom-driver seam + MissingExtraError + caching."""

from __future__ import annotations

import pytest

from arvel.support.manager import Manager, MissingExtraError


class DemoManager(Manager):
    def default_driver(self) -> str:
        return "memory"

    def create_memory_driver(self) -> dict[str, str]:
        return {"kind": "memory"}


def test_extend_registers_a_custom_driver() -> None:
    manager = DemoManager()
    manager.extend("custom", lambda app: {"kind": "custom", "app": str(app)})
    assert manager.driver("custom") == {"kind": "custom", "app": "None"}
    assert manager.driver("memory") == {"kind": "memory"}  # built-in still resolves


def test_extend_takes_precedence_over_builtin() -> None:
    manager = DemoManager()
    manager.extend("memory", lambda _app: {"kind": "overridden"})
    assert manager.driver("memory") == {"kind": "overridden"}


def test_unknown_driver_raises_missing_extra() -> None:
    manager = DemoManager()
    with pytest.raises(MissingExtraError, match="nonexistent"):
        manager.driver("nonexistent")


def test_resolved_driver_is_cached() -> None:
    manager = DemoManager()
    assert manager.driver("memory") is manager.driver("memory")
