"""BroadcastServiceProvider."""

from __future__ import annotations


def test_provider_registers_manager_and_facade() -> None:
    """+: register binds BroadcastManager and wires the Broadcast facade."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.container import Container
    from arvel.facades.broadcast import Broadcast
    from arvel.providers.broadcast_provider import BroadcastServiceProvider

    container = Container()
    container.instance(BroadcastConfig, BroadcastConfig(default=BroadcastDriver.NULL))

    class _FakeApp:
        def __init__(self, c: Container) -> None:
            self.container: Container = c

    provider = BroadcastServiceProvider(_FakeApp(container))  # type: ignore[arg-type]
    provider.register()

    assert container.bound(BroadcastManager)
    assert container.make(BroadcastManager) is not None
    assert Broadcast.driver() is not None
    Broadcast.set_manager(None)


def test_provider_registers_console_commands() -> None:
    """provider.commands returns the reverb:start command."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.container import Container
    from arvel.providers.broadcast_provider import BroadcastServiceProvider

    container = Container()
    container.instance(BroadcastConfig, BroadcastConfig(default=BroadcastDriver.NULL))

    class _FakeApp:
        def __init__(self, c: Container) -> None:
            self.container: Container = c

    provider = BroadcastServiceProvider(_FakeApp(container))  # type: ignore[arg-type]
    commands = provider.commands()
    names = [getattr(c, "__name__", type(c).__name__) for c in commands]
    assert any("Reverb" in n for n in names)


def test_provider_uses_default_config_when_unbound() -> None:
    """provider gracefully creates default BroadcastConfig when not bound."""
    from arvel.broadcasting.config import BroadcastConfig
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.container import Container
    from arvel.facades.broadcast import Broadcast
    from arvel.providers.broadcast_provider import BroadcastServiceProvider

    container = Container()  # no BroadcastConfig pre-bound

    class _FakeApp:
        def __init__(self, c: Container) -> None:
            self.container: Container = c

    provider = BroadcastServiceProvider(_FakeApp(container))  # type: ignore[arg-type]
    provider.register()

    assert container.bound(BroadcastConfig)
    assert isinstance(container.make(BroadcastManager), BroadcastManager)
    Broadcast.set_manager(None)
