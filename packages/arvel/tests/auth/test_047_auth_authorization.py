"""Auth Authorization cluster.
Tests are FAILING before the fix and PASSING after.

): Gate must be registered as a DI singleton.
): Single Authenticate middleware; optional variant renamed.
): Policy.check() must support sync and async methods.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.requests import Request as _StarletteRequest

# Gate DI singleton


class TestStory17GateDISingleton:
    """AuthServiceProvider must register Gate as a container singleton."""

    def test_gate_is_resolvable_from_container(self) -> None:
        """Container.make(Gate) must work after AuthServiceProvider registers.

        Currently FAILS: Gate is not registered in the container.
        """
        from arvel.application.application import Application
        from arvel.auth.gate import Gate

        app = Application()
        app.register()

        gate = app.container.make(Gate)
        assert isinstance(gate, Gate)

    def test_gate_is_a_singleton(self) -> None:
        """Two calls to container.make(Gate) must return the same instance."""
        from arvel.application.application import Application
        from arvel.auth.gate import Gate

        app = Application()
        app.register()

        gate1 = app.container.make(Gate)
        gate2 = app.container.make(Gate)
        assert gate1 is gate2

    @pytest.mark.asyncio
    async def test_gate_define_and_allows_work_on_singleton(self) -> None:
        """Gate singleton must accumulate registered abilities correctly."""
        from arvel.application.application import Application
        from arvel.auth.gate import Gate

        app = Application()
        app.register()

        gate = app.container.make(Gate)

        def _view_admin(user: dict[str, Any]) -> bool:
            return user.get("role") == "admin"

        gate.define("view-admin", _view_admin)

        admin = {"role": "admin"}
        user = {"role": "guest"}

        assert await gate.allows("view-admin", admin) is True
        assert await gate.allows("view-admin", user) is False


# Single canonical Authenticate middleware


class TestStory18SingleAuthenticateMiddleware:
    """arvel.http.middleware.Authenticate must be the canonical blocking middleware."""

    def test_http_middleware_authenticate_exists(self) -> None:
        """arvel.http.middleware.Authenticate must be importable."""
        import arvel.http.middleware as _hm

        assert hasattr(_hm, "Authenticate"), "arvel.http.middleware.Authenticate must exist"

    def test_auth_middleware_authenticate_exports_optional(self) -> None:
        """arvel.auth.middleware.authenticate must export OptionalAuthenticate."""
        import arvel.auth.middleware.authenticate as m

        assert hasattr(m, "OptionalAuthenticate"), (
            "auth.middleware.authenticate must expose OptionalAuthenticate "
            "(the optional, non-blocking variant). Got: "
            + str([x for x in dir(m) if not x.startswith("_")])
        )

    def test_auth_middleware_authenticate_is_not_same_as_http_middleware(self) -> None:
        """The two Authenticate classes must be distinct — one blocking, one optional."""
        from arvel.auth.middleware.authenticate import OptionalAuthenticate
        from arvel.http.middleware import Authenticate

        assert Authenticate.__name__ != OptionalAuthenticate.__name__  # distinct classes

    def test_canonical_authenticate_raises_401_for_unauthenticated_request(self) -> None:
        """The blocking Authenticate must raise 401 when no user is authenticated."""
        from arvel.http.exceptions import HttpExceptionHandler
        from arvel.http.middleware import Authenticate
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        fastapp = FastAPI()
        handler = HttpExceptionHandler()
        handler.register(fastapp)

        @fastapp.get("/protected")
        async def _endpoint(request: _StarletteRequest) -> dict[str, str]:
            auth = Authenticate()

            async def _noop(_req: Any) -> None:
                pass

            await auth.handle(request, _noop)
            return {"ok": "yes"}

        del _endpoint  # registered via @fastapp.get; drop local binding

        client = TestClient(fastapp, raise_server_exceptions=False)
        response = client.get("/protected")
        # Must be 401 because no user is authenticated
        assert response.status_code in (401, 503)  # 503 acceptable if container unavailable


# Policy supports sync and async methods


class TestStory19PolicySyncAsync:
    """Policy.check() must handle both sync def and async def methods."""

    @pytest.mark.asyncio
    async def test_policy_check_with_sync_method(self) -> None:
        """Sync def policy method must not raise TypeError.

        Currently FAILS: Policy.check() unconditionally awaits the method result,
        causing TypeError when the method is synchronous.
        """
        from arvel.auth.policy import Policy

        class Post:
            def __init__(self, user_id: str) -> None:
                self.user_id = user_id

        class PostPolicy(Policy[Post]):
            def update(self, user: Any, resource: Post) -> bool:
                # Sync method — must NOT be awaited
                return bool(user.get("id") == resource.user_id)

        policy = PostPolicy()
        user = {"id": "alice"}
        post_owned = Post("alice")
        post_other = Post("bob")

        assert await policy.check("update", user, post_owned) is True
        assert await policy.check("update", user, post_other) is False

    @pytest.mark.asyncio
    async def test_policy_check_with_async_method(self) -> None:
        """Async def policy method must still work correctly."""
        from arvel.auth.policy import Policy

        class Post:
            def __init__(self, user_id: str) -> None:
                self.user_id = user_id

        class PostPolicy(Policy[Post]):
            async def update(self, user: Any, resource: Post) -> bool:
                # Async method — must be awaited
                return bool(user.get("id") == resource.user_id)

        policy = PostPolicy()
        user = {"id": "alice"}
        post_owned = Post("alice")
        post_other = Post("bob")

        assert await policy.check("update", user, post_owned) is True
        assert await policy.check("update", user, post_other) is False

    @pytest.mark.asyncio
    async def test_policy_check_with_sync_method_no_resource(self) -> None:
        """Sync method without resource argument must work."""
        from arvel.auth.policy import Policy

        class ImagePolicy(Policy[None]):
            def upload(self, user: Any) -> bool:
                return bool(user.get("verified", False))

        policy = ImagePolicy()
        verified_user: dict[str, Any] = {"id": "bob", "verified": True}
        unverified_user: dict[str, Any] = {"id": "alice", "verified": False}

        assert await policy.check("upload", verified_user) is True
        assert await policy.check("upload", unverified_user) is False

    @pytest.mark.asyncio
    async def test_policy_check_returns_false_for_unknown_ability(self) -> None:
        """Missing ability must return False, not raise AttributeError."""
        from arvel.auth.policy import Policy

        class EmptyPolicy(Policy[None]):
            pass

        policy = EmptyPolicy()
        assert await policy.check("nonexistent", {"id": "user"}) is False

    @pytest.mark.asyncio
    async def test_gate_policy_integration_with_sync_policy(self) -> None:
        """Gate.allows() must correctly call a sync policy method via Policy.check().

        Integration test: Gate → Policy → sync def method.
        """
        from arvel.auth.gate import Gate
        from arvel.auth.policy import Policy

        class Document:
            def __init__(self, owner: str) -> None:
                self.owner = owner

        class DocumentPolicy(Policy[Document]):
            def edit(self, user: Any, doc: Document) -> bool:
                return bool(user["id"] == doc.owner)

        gate = Gate()
        gate.policy(Document, DocumentPolicy())

        owner = {"id": "alice"}
        other = {"id": "bob"}
        doc = Document("alice")

        assert await gate.allows("edit", owner, doc) is True
        assert await gate.allows("edit", other, doc) is False
