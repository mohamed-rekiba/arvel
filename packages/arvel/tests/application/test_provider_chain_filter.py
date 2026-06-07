"""``filter_provider_chain`` — subsystem-aware filter for the bootstrap chain.

Drops providers whose ``subsystem`` is not in ``required``, with carve-outs
for the tail (Console) and for untagged or tagged user providers.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.application.application import filter_provider_chain
from arvel.console._subsystem import CliSubsystem
from arvel.console.providers.console_service_provider import ConsoleServiceProvider
from arvel.providers import ServiceProvider


class _UserUntagged(ServiceProvider):
    subsystem: ClassVar[CliSubsystem | None] = None


class _DefensiveUntagged(ServiceProvider):
    # Untagged, not a user provider, not Console — the "defensive" branch.
    subsystem: ClassVar[CliSubsystem | None] = None


class _DatabaseFramework(ServiceProvider):
    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.DATABASE


class _CacheFramework(ServiceProvider):
    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.CACHE


class _DatabaseUserProvider(ServiceProvider):
    # User provider that happens to tag itself with a known subsystem.
    subsystem: ClassVar[CliSubsystem | None] = CliSubsystem.DATABASE


def test_keeps_provider_whose_subsystem_is_required() -> None:
    out = filter_provider_chain(
        [_DatabaseFramework, _CacheFramework],
        required=frozenset({CliSubsystem.DATABASE}),
        user_classes=[],
    )
    assert out == [_DatabaseFramework]


def test_keeps_console_tail_even_when_no_subsystem_requested() -> None:
    out = filter_provider_chain(
        [_DatabaseFramework, ConsoleServiceProvider],
        required=frozenset(),
        user_classes=[],
    )
    assert out == [ConsoleServiceProvider]


def test_keeps_untagged_user_provider_when_user_providers_required() -> None:
    out = filter_provider_chain(
        [_UserUntagged],
        required=frozenset({CliSubsystem.USER_PROVIDERS}),
        user_classes=[_UserUntagged],
    )
    assert out == [_UserUntagged]


def test_drops_untagged_user_provider_when_user_providers_not_required() -> None:
    out = filter_provider_chain(
        [_UserUntagged],
        required=frozenset({CliSubsystem.DATABASE}),
        user_classes=[_UserUntagged],
    )
    assert out == []


def test_keeps_untagged_non_user_non_console_provider_defensively() -> None:
    # Anything untagged that isn't tail or user gets kept — the comment in the
    # source calls this the "defensive" branch and notes only Console belongs here.
    out = filter_provider_chain(
        [_DefensiveUntagged],
        required=frozenset({CliSubsystem.DATABASE}),
        user_classes=[],
    )
    assert out == [_DefensiveUntagged]


def test_keeps_tagged_user_provider_when_user_providers_required() -> None:
    # Tagged with DATABASE but DATABASE is not in `required`; USER_PROVIDERS is.
    # The user-provider branch (line 145) keeps it.
    out = filter_provider_chain(
        [_DatabaseUserProvider],
        required=frozenset({CliSubsystem.USER_PROVIDERS}),
        user_classes=[_DatabaseUserProvider],
    )
    assert out == [_DatabaseUserProvider]


def test_drops_tagged_user_provider_when_neither_subsystem_required() -> None:
    out = filter_provider_chain(
        [_DatabaseUserProvider],
        required=frozenset({CliSubsystem.CACHE}),
        user_classes=[_DatabaseUserProvider],
    )
    assert out == []


def test_preserves_chain_order() -> None:
    chain: list[type[ServiceProvider]] = [
        _DatabaseFramework,
        _UserUntagged,
        _CacheFramework,
        ConsoleServiceProvider,
    ]
    out = filter_provider_chain(
        chain,
        required=frozenset(
            {CliSubsystem.DATABASE, CliSubsystem.CACHE, CliSubsystem.USER_PROVIDERS}
        ),
        user_classes=[_UserUntagged],
    )
    assert out == chain
