"""Failing tests for Explicit Route Model Binding.

— ``Route.bind(name, resolver)`` registers a custom resolver
keyed by URL parameter name. The resolver wins over implicit ``Model`` binding
and runs at request time with the raw URL string. A return of ``None`` produces
a 404; any other value is injected into the handler under the parameter name.

Run BEFORE implementation — every integration test in this file MUST fail
(RED state).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
import pytest_asyncio
from arvel.database import Model, id_, string
from arvel.http.middleware.database_transaction import DatabaseTransaction
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class _Widget(Model):
    __tablename__ = "wi056_widgets"

    route_key_name: ClassVar[str] = "slug"

    id: int = id_()
    slug: str = string(80, unique=True)
    label: str = string(80)


@pytest_asyncio.fixture
async def bind_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as s:
        s.add_all(
            [
                _Widget(slug="one", label="One"),
                _Widget(slug="two", label="Two"),
            ]
        )
        await s.commit()

    try:
        yield maker
    finally:
        await engine.dispose()


# Unit tests: registry


class TestBindingRegistry:
    """``Route.bind`` records resolvers and surfaces them via the Router."""

    def test_bind_records_global_resolver(self) -> None:
        from arvel.routing import Route, Router

        Router.reset_singleton()

        async def _resolve(value: str) -> dict[str, str]:
            return {"slug": value}

        Route.bind("widget", _resolve)
        resolvers = Router.singleton().bindings()
        assert "widget" in resolvers
        assert resolvers["widget"] is _resolve

    def test_router_reset_clears_bindings(self) -> None:
        from arvel.routing import Route, Router

        Router.reset_singleton()

        async def _resolve(value: str) -> str:
            return value

        Route.bind("foo", _resolve)
        assert "foo" in Router.singleton().bindings()
        Router.reset_singleton()
        assert "foo" not in Router.singleton().bindings()


# Integration tests


@pytest.mark.usefixtures("bind_db")
class TestExplicitBindingResolves:
    def _client(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        handler: Any,
        *,
        path: str,
    ) -> Any:
        from arvel.http.exceptions import HttpExceptionHandler
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        tx = DatabaseTransaction(session_maker=session_maker)
        Route.get(path, middleware=[tx])(handler)

        app = FastAPI()
        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)
        return TestClient(app)

    def test_resolver_overrides_implicit_binding(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        """Even though `widget: _Widget` has implicit binding via slug, the
        explicit resolver wins and gets to inspect the raw URL value."""
        from arvel.routing import Route, Router

        Router.reset_singleton()
        captured: list[str] = []

        async def _custom(raw: str) -> _Widget | None:
            captured.append(raw)
            return await _Widget.where(slug=raw.upper().lower()).first()

        Route.bind("widget", _custom)

        async def show(widget: _Widget) -> dict[str, Any]:
            return {"slug": widget.slug, "label": widget.label}

        client = self._client(bind_db, show, path="/widgets/{widget}")
        resp = client.get("/widgets/one")
        assert resp.status_code == 200
        assert resp.json() == {"slug": "one", "label": "One"}
        assert captured == ["one"]

    def test_resolver_returning_none_yields_404(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        from arvel.routing import Route, Router

        Router.reset_singleton()

        async def _custom(_raw: str) -> _Widget | None:
            return None

        Route.bind("widget", _custom)

        async def show(widget: _Widget) -> dict[str, Any]:
            return {"slug": widget.slug}

        client = self._client(bind_db, show, path="/widgets/{widget}")
        resp = client.get("/widgets/anything")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "NOT_FOUND"

    def test_resolver_runs_even_for_non_model_param_annotations(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        """Explicit binding doesn't require a Model-typed param."""
        from arvel.routing import Route, Router

        Router.reset_singleton()

        async def _custom(raw: str) -> dict[str, str]:
            return {"raw": raw, "uppercased": raw.upper()}

        Route.bind("token", _custom)

        async def show(token: dict[str, str]) -> dict[str, str]:
            return token

        client = self._client(bind_db, show, path="/tokens/{token}")
        resp = client.get("/tokens/abc")
        assert resp.status_code == 200
        assert resp.json() == {"raw": "abc", "uppercased": "ABC"}


# Group-scoped bindings


@pytest.mark.usefixtures("bind_db")
def test_group_scoped_binding_applies_only_inside_group(
    bind_db: async_sessionmaker[AsyncSession],
) -> None:
    """A binding declared inside ``with Route.group()`` is scoped to that group."""
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()
    tx = DatabaseTransaction(session_maker=bind_db)

    inside_calls: list[str] = []
    outside_calls: list[str] = []

    with Route.group(prefix="/inside", middleware=[tx]):

        async def _scoped(raw: str) -> _Widget | None:
            inside_calls.append(raw)
            return await _Widget.where(slug=raw).first()

        Route.bind("widget", _scoped)

        @Route.get("/widgets/{widget}")
        async def _scoped_show(widget: _Widget) -> dict[str, Any]:
            return {"slug": widget.slug, "where": "inside"}

        del _scoped_show

    # Outside the group: same param name `widget`, but no resolver should fire
    # implicit binding (via slug, since _Widget.route_key_name == "slug") takes over.
    @Route.get("/outside/widgets/{widget}", middleware=[tx])
    async def _outside_show(widget: _Widget) -> dict[str, Any]:
        outside_calls.append(widget.slug)
        return {"slug": widget.slug, "where": "outside"}

    del _outside_show

    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    client = TestClient(app)

    resp_in = client.get("/inside/widgets/two")
    assert resp_in.status_code == 200
    assert resp_in.json() == {"slug": "two", "where": "inside"}
    assert inside_calls == ["two"]

    resp_out = client.get("/outside/widgets/one")
    assert resp_out.status_code == 200
    assert resp_out.json() == {"slug": "one", "where": "outside"}
    assert outside_calls == ["one"]


@pytest.mark.usefixtures("bind_db")
def test_nested_group_binding_overrides_outer_binding(
    bind_db: async_sessionmaker[AsyncSession],
) -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()
    tx = DatabaseTransaction(session_maker=bind_db)

    outer_calls = 0
    inner_calls = 0

    with Route.group(prefix="/v1", middleware=[tx]):

        async def _outer(raw: str) -> _Widget | None:
            nonlocal outer_calls
            outer_calls += 1
            return await _Widget.where(slug=raw).first()

        Route.bind("widget", _outer)

        with Route.group(prefix="/admin"):

            async def _inner(raw: str) -> _Widget | None:
                nonlocal inner_calls
                inner_calls += 1
                # Admin sees rows by uppercased slug — purely synthetic for the test.
                return await _Widget.where(slug=raw.lower()).first()

            Route.bind("widget", _inner)

            @Route.get("/widgets/{widget}")
            async def _admin_show(widget: _Widget) -> dict[str, Any]:
                return {"slug": widget.slug, "scope": "admin"}

            del _admin_show

        @Route.get("/widgets/{widget}")
        async def _public_show(widget: _Widget) -> dict[str, Any]:
            return {"slug": widget.slug, "scope": "public"}

        del _public_show

    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    client = TestClient(app)

    resp_admin = client.get("/v1/admin/widgets/ONE")
    assert resp_admin.status_code == 200
    assert resp_admin.json() == {"slug": "one", "scope": "admin"}
    assert inner_calls == 1
    assert outer_calls == 0

    resp_public = client.get("/v1/widgets/two")
    assert resp_public.status_code == 200
    assert resp_public.json() == {"slug": "two", "scope": "public"}
    assert outer_calls == 1


@pytest.mark.usefixtures("bind_db")
def test_global_binding_visible_to_routes_inside_group(
    bind_db: async_sessionmaker[AsyncSession],
) -> None:
    """A global ``Route.bind`` outside any group is honoured by routes declared
    inside a group, unless the group overrides it."""
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()
    tx = DatabaseTransaction(session_maker=bind_db)
    seen: list[str] = []

    async def _global(raw: str) -> _Widget | None:
        seen.append(raw)
        return await _Widget.where(slug=raw).first()

    Route.bind("widget", _global)

    with Route.group(prefix="/api", middleware=[tx]):

        @Route.get("/widgets/{widget}")
        async def _show(widget: _Widget) -> dict[str, Any]:
            return {"slug": widget.slug}

        del _show

    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)
    client = TestClient(app)

    resp = client.get("/api/widgets/one")
    assert resp.status_code == 200
    assert resp.json() == {"slug": "one"}
    assert seen == ["one"]
