"""Subsystem needs for provider-attached commands that aren't entry points.

The queue worker family (``queue:work``, ``queue:failed``, ...) is built with DI
inside ``QueueServiceProvider.commands()``, so it can't be an ``arvel.commands``
entry point and ``load_command()`` can't resolve it by name. Without this map the
entrypoint can't know a provider command's subsystems without booting every
provider first — so ``arvel queue:work`` would boot the full chain (HTTP,
scheduler, observability, ...) just to run a worker.

Keyed by command name -> the raw ``Command.requires`` the class declares (the
caller applies ``closure()``). A drift-guard test boots a full app, finds every
provider command that isn't an entry point, and asserts it appears here with
matching ``requires`` — so a new provider-only command can't silently regress to
a full boot.
"""

from __future__ import annotations

from arvel.console._subsystem import CliSubsystem

PROVIDER_COMMAND_REQUIRES: dict[str, frozenset[CliSubsystem]] = {
    "queue:work": frozenset(
        {CliSubsystem.QUEUE, CliSubsystem.CACHE, CliSubsystem.USER_PROVIDERS}
    ),
    "queue:failed": frozenset({CliSubsystem.QUEUE, CliSubsystem.USER_PROVIDERS}),
    "queue:retry": frozenset({CliSubsystem.QUEUE, CliSubsystem.USER_PROVIDERS}),
    "queue:flush": frozenset({CliSubsystem.QUEUE, CliSubsystem.USER_PROVIDERS}),
    "queue:forget": frozenset({CliSubsystem.QUEUE, CliSubsystem.USER_PROVIDERS}),
    "queue:size": frozenset({CliSubsystem.QUEUE, CliSubsystem.USER_PROVIDERS}),
}

__all__ = ["PROVIDER_COMMAND_REQUIRES"]
