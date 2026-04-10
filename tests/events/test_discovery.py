"""Tests for Listener Discovery — Story 2.

FR-006: Auto-discovery from module listeners/ directories.
FR-007: Explicit registration via provider boot().
FR-008: Invalid listener files skipped with warning.
SEC: Discovery does not execute arbitrary code from non-listener files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class TestListenerAutoDiscovery:
    """FR-006: Listeners auto-discovered from module listeners/ dirs."""

    async def test_discovers_listener_with_type_hint(self, tmp_path: Path) -> None:
        """Given a module with listeners/send_welcome.py containing a
        Listener subclass with handle(self, event: UserRegistered),
        discovery registers it for UserRegistered.
        """
        from arvel.events.discovery import discover_listeners

        module_dir = tmp_path / "app" / "modules" / "users"
        listeners_dir = module_dir / "listeners"
        listeners_dir.mkdir(parents=True)
        (module_dir / "__init__.py").write_text("")
        (listeners_dir / "__init__.py").write_text("")
        (listeners_dir / "send_welcome.py").write_text(
            "from arvel.events.listener import Listener\n"
            "from tests.events.conftest import UserRegistered\n\n"
            "class SendWelcome(Listener):\n"
            "    async def handle(self, event: UserRegistered) -> None:\n"
            "        pass\n"
        )

        discovered = discover_listeners(tmp_path / "app" / "modules")
        assert len(discovered) >= 1

    async def test_discovers_multiple_listeners(self, tmp_path: Path) -> None:
        """Multiple listener files in the same module are all discovered."""
        from arvel.events.discovery import discover_listeners

        module_dir = tmp_path / "app" / "modules" / "users"
        listeners_dir = module_dir / "listeners"
        listeners_dir.mkdir(parents=True)
        (module_dir / "__init__.py").write_text("")
        (listeners_dir / "__init__.py").write_text("")

        for name in ("listener_a", "listener_b"):
            (listeners_dir / f"{name}.py").write_text(
                "from arvel.events.listener import Listener\n"
                "from tests.events.conftest import UserRegistered\n\n"
                f"class {name.title().replace('_', '')}(Listener):\n"
                "    async def handle(self, event: UserRegistered) -> None:\n"
                "        pass\n"
            )

        discovered = discover_listeners(tmp_path / "app" / "modules")
        assert len(discovered) >= 2

    async def test_discovers_across_modules(self, tmp_path: Path) -> None:
        """Listeners from different modules are all discovered."""
        from arvel.events.discovery import discover_listeners

        for mod_name in ("users", "billing"):
            module_dir = tmp_path / "app" / "modules" / mod_name
            listeners_dir = module_dir / "listeners"
            listeners_dir.mkdir(parents=True)
            (module_dir / "__init__.py").write_text("")
            (listeners_dir / "__init__.py").write_text("")
            (listeners_dir / "handler.py").write_text(
                "from arvel.events.listener import Listener\n"
                "from tests.events.conftest import UserRegistered\n\n"
                f"class {mod_name.title()}Handler(Listener):\n"
                "    async def handle(self, event: UserRegistered) -> None:\n"
                "        pass\n"
            )

        discovered = discover_listeners(tmp_path / "app" / "modules")
        assert len(discovered) >= 2


class TestExplicitRegistration:
    """FR-007: Provider boot() can explicitly register listeners."""

    async def test_explicit_registration_via_register(self) -> None:
        from arvel.events.dispatcher import EventDispatcher

        from .conftest import SendWelcomeEmail, UserRegistered

        dispatcher = EventDispatcher()
        dispatcher.register(UserRegistered, SendWelcomeEmail)

        listeners = dispatcher.listeners_for(UserRegistered)
        assert SendWelcomeEmail in listeners


class TestInvalidListenerSkipped:
    """FR-008: Invalid listener files skipped with warning."""

    async def test_non_listener_file_skipped(self, tmp_path: Path) -> None:
        """A .py file in listeners/ that doesn't subclass Listener is skipped."""
        from arvel.events.discovery import discover_listeners

        module_dir = tmp_path / "app" / "modules" / "users"
        listeners_dir = module_dir / "listeners"
        listeners_dir.mkdir(parents=True)
        (module_dir / "__init__.py").write_text("")
        (listeners_dir / "__init__.py").write_text("")
        (listeners_dir / "not_a_listener.py").write_text("x = 42\n")

        discovered = discover_listeners(tmp_path / "app" / "modules")
        assert len(discovered) == 0

    async def test_module_without_listeners_dir_skipped(self, tmp_path: Path) -> None:
        """A module without a listeners/ directory is silently skipped."""
        from arvel.events.discovery import discover_listeners

        module_dir = tmp_path / "app" / "modules" / "users"
        module_dir.mkdir(parents=True)
        (module_dir / "__init__.py").write_text("")

        discovered = discover_listeners(tmp_path / "app" / "modules")
        assert len(discovered) == 0

    async def test_dunder_files_ignored(self, tmp_path: Path) -> None:
        """__init__.py and __pycache__ files in listeners/ are ignored."""
        from arvel.events.discovery import discover_listeners

        module_dir = tmp_path / "app" / "modules" / "users"
        listeners_dir = module_dir / "listeners"
        listeners_dir.mkdir(parents=True)
        (module_dir / "__init__.py").write_text("")
        (listeners_dir / "__init__.py").write_text("")

        discovered = discover_listeners(tmp_path / "app" / "modules")
        assert len(discovered) == 0
