"""CLI subsystem taxonomy and dependency closure.

A "subsystem" is a self-contained boot unit (one ``ServiceProvider`` per
subsystem). Every CLI command declares the subsystems it needs via
``Command.requires``; the entrypoint computes the transitive closure under
the dependency graph below and boots only those providers.

Adding a new subsystem:

1. Add a member to :class:`CliSubsystem`.
2. Tag the provider that serves it with the matching ``subsystem`` ClassVar.
3. If it depends on another subsystem, add an edge to ``_DEPENDENCY_EDGES``.
4. Tag every command that uses it via ``requires``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class CliSubsystem(StrEnum):
    """Stable identifier for a CLI bootstrap subsystem.

    Values are kebab-case for stable log/CLI surface. Don't rename without
    updating every ``Command.requires`` and ``ServiceProvider.subsystem``.
    """

    CONFIG = "config"
    LOG = "log"
    LANG = "lang"
    CONTEXT = "context"

    OBSERVABILITY = "observability"
    DATABASE = "database"
    HTTP = "http"
    SCHEDULER = "scheduler"
    QUEUE = "queue"
    CACHE = "cache"
    MAIL = "mail"
    STORAGE = "storage"
    BROADCAST = "broadcast"
    AUTH = "auth"
    EVENTS = "events"

    USER_PROVIDERS = "user_providers"


FOUNDATION_SUBSYSTEMS: frozenset[CliSubsystem] = frozenset(
    {
        CliSubsystem.CONFIG,
        CliSubsystem.LOG,
        CliSubsystem.LANG,
        CliSubsystem.CONTEXT,
    }
)
"""Always-on subsystems. Bootstrap adds these to every closure.

Cheap (no I/O), and every other subsystem relies on at least one of them.
"""


_DEPENDENCY_EDGES: dict[CliSubsystem, frozenset[CliSubsystem]] = {
    CliSubsystem.QUEUE: frozenset({CliSubsystem.DATABASE}),
    CliSubsystem.AUTH: frozenset({CliSubsystem.DATABASE}),
}


# DFS coloring sentinels for cycle detection.
_WHITE: Final[int] = 0
_GRAY: Final[int] = 1
_BLACK: Final[int] = 2


def validate_no_cycles() -> None:
    """Tarjan-lite cycle check. Run at import; fail loud if a cycle exists.

    Cycles in the bootstrap graph would silently deadlock provider boot.
    """
    color: dict[CliSubsystem, int] = dict.fromkeys(CliSubsystem, _WHITE)

    def visit(node: CliSubsystem, stack: list[CliSubsystem]) -> None:
        color[node] = _GRAY
        stack.append(node)
        for dep in _DEPENDENCY_EDGES.get(node, frozenset()):
            if color[dep] == _GRAY:
                cycle = " -> ".join(s.value for s in [*stack, dep])
                msg = f"CliSubsystem dependency cycle: {cycle}"
                raise RuntimeError(msg)
            if color[dep] == _WHITE:
                visit(dep, stack)
        stack.pop()
        color[node] = _BLACK

    for node in CliSubsystem:
        if color[node] == _WHITE:
            visit(node, [])


validate_no_cycles()


def closure(requires: frozenset[CliSubsystem]) -> frozenset[CliSubsystem]:
    """Return ``requires`` plus every transitive dependency.

    Does NOT inject foundation subsystems — that's the bootstrap's job (it
    always merges :data:`FOUNDATION_SUBSYSTEMS` into the boot set). Keeping
    this function pure makes it easy to unit-test the graph in isolation.

    Returns ``frozenset()`` when ``requires`` is empty.
    """
    if not requires:
        return frozenset()

    seen: set[CliSubsystem] = set()
    stack: list[CliSubsystem] = list(requires)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(_DEPENDENCY_EDGES.get(node, frozenset()))
    return frozenset(seen)


__all__ = ["FOUNDATION_SUBSYSTEMS", "CliSubsystem", "closure"]
