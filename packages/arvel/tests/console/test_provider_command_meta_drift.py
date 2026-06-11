"""Drift guard for ``console/_provider_command_meta.py``.

Provider-attached commands (DI ``__init__``, not ``arvel.commands`` entry points)
need a static name->requires map so the entrypoint boots just their subsystems
instead of the full chain. Today only ``QueueServiceProvider`` ships such
commands. If another provider adds a DI-constructed command, extend both
``PROVIDER_COMMAND_REQUIRES`` and this test.
"""

from __future__ import annotations

from arvel import Application
from arvel.console import Command
from arvel.console._loader import entry_point_names
from arvel.console._provider_command_meta import PROVIDER_COMMAND_REQUIRES
from arvel.console._subsystem import CliSubsystem
from arvel.queue.providers.queue_service_provider import QueueServiceProvider


def _provider_only_commands() -> dict[str, frozenset[CliSubsystem]]:
    """Name -> class ``requires`` for queue commands that aren't entry points."""
    app = Application()
    provider = QueueServiceProvider(app)
    provider.register()  # binds QueueManager + FailedJobStore so commands() resolves
    entry_points = set(entry_point_names())
    out: dict[str, frozenset[CliSubsystem]] = {}
    for cmd in provider.commands():
        # commands() is typed list[Any] on the queue provider; narrow to the class.
        cls: type[Command] = cmd if isinstance(cmd, type) else type(cmd)
        if cls.name not in entry_points:
            out[cls.name] = cls.requires
    return out


def test_manifest_covers_every_provider_only_command() -> None:
    live = _provider_only_commands()
    assert set(PROVIDER_COMMAND_REQUIRES) == set(live)


def test_manifest_requires_match_class_requires() -> None:
    for name, class_requires in _provider_only_commands().items():
        assert PROVIDER_COMMAND_REQUIRES[name] == class_requires
