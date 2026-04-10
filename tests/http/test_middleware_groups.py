"""Tests for middleware groups — Story 4.

FR-050: Named middleware groups expand to multiple aliases
FR-051: Groups defined in HttpSettings are available at boot
FR-052: Group + individual middleware ordering
FR-053: Recursive group expansion
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from arvel.http.config import HttpSettings
from arvel.http.exceptions import MiddlewareResolutionError
from arvel.http.middleware import MiddlewareStack

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class _StubMiddlewareA:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class _StubMiddlewareB:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class _StubMiddlewareC:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)


class TestMiddlewareGroupExpansion:
    """FR-050: Named middleware groups expand to individual aliases."""

    def test_group_expands_to_individual_aliases(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "throttle": f"{__name__}._StubMiddlewareA",
                "auth": f"{__name__}._StubMiddlewareB",
            },
            groups={"api": ["throttle", "auth"]},
        )

        expanded = stack.expand(["api"])
        assert expanded == ["throttle", "auth"]

    def test_group_resolve_returns_correct_classes(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "throttle": f"{__name__}._StubMiddlewareA",
                "auth": f"{__name__}._StubMiddlewareB",
            },
            groups={"api": ["throttle", "auth"]},
        )

        resolved = stack.resolve(["api"])
        assert len(resolved) == 2
        assert resolved[0] is _StubMiddlewareA
        assert resolved[1] is _StubMiddlewareB

    def test_group_plus_individual_middleware(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "throttle": f"{__name__}._StubMiddlewareA",
                "auth": f"{__name__}._StubMiddlewareB",
                "log": f"{__name__}._StubMiddlewareC",
            },
            groups={"api": ["throttle", "auth"]},
        )

        resolved = stack.resolve(["api", "log"])
        assert len(resolved) == 3
        assert resolved[0] is _StubMiddlewareA
        assert resolved[1] is _StubMiddlewareB
        assert resolved[2] is _StubMiddlewareC

    def test_non_group_name_passes_through(self) -> None:
        stack = MiddlewareStack(
            aliases={"auth": f"{__name__}._StubMiddlewareA"},
            groups={},
        )

        expanded = stack.expand(["auth"])
        assert expanded == ["auth"]


class TestRecursiveGroupExpansion:
    """FR-053: Groups can reference other groups recursively."""

    def test_nested_group_expansion(self) -> None:
        stack = MiddlewareStack(
            aliases={
                "throttle": f"{__name__}._StubMiddlewareA",
                "auth": f"{__name__}._StubMiddlewareB",
                "log": f"{__name__}._StubMiddlewareC",
            },
            groups={
                "security": ["throttle", "auth"],
                "api": ["security", "log"],
            },
        )

        expanded = stack.expand(["api"])
        assert expanded == ["throttle", "auth", "log"]

    def test_circular_group_reference_raises(self) -> None:
        stack = MiddlewareStack(
            aliases={},
            groups={
                "a": ["b"],
                "b": ["a"],
            },
        )

        with pytest.raises(MiddlewareResolutionError, match="Circular"):
            stack.expand(["a"])

    def test_self_referencing_group_raises(self) -> None:
        stack = MiddlewareStack(
            aliases={},
            groups={"loop": ["loop"]},
        )

        with pytest.raises(MiddlewareResolutionError, match="Circular"):
            stack.expand(["loop"])


class TestHttpSettingsMiddlewareGroups:
    """FR-051: Groups defined in HttpSettings."""

    def test_default_groups_is_empty(self) -> None:
        settings = HttpSettings()
        assert settings.middleware_groups == {}

    def test_groups_can_be_configured(self) -> None:
        settings = HttpSettings(
            middleware_groups={
                "api": ["throttle", "auth"],
                "web": ["csrf", "session"],
            },
        )
        assert settings.middleware_groups["api"] == ["throttle", "auth"]
        assert settings.middleware_groups["web"] == ["csrf", "session"]
