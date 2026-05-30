"""Failing tests for WI-arvel-055: Implicit Route Model Binding.

Epic 048 Story 1 — FastAPI route parameters typed with a ``Model`` subclass
auto-resolve from the database. Hit ``/posts/5`` with ``def show(post: Post)``
and the handler sees a fully-loaded ``Post`` instance. Miss the row → 404.

Run BEFORE implementation — every test in this file MUST fail (Red state).
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
import pytest_asyncio
from arvel.database import Model
from arvel.http.middleware.database_transaction import DatabaseTransaction
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


# ─────────────────────────── Test fixtures: models ──────────────────────────


class _BindPost(Model):
    """Standard model — bound by integer primary key."""

    __tablename__ = "wi055_bind_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80), nullable=False)


class _BindArticle(Model):
    """Slug-bound model — overrides ``route_key_name``."""

    __tablename__ = "wi055_bind_articles"

    route_key_name: ClassVar[str] = "slug"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    body: Mapped[str] = mapped_column(String(255), nullable=False)


@pytest_asyncio.fixture
async def bind_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Per-test engine with the WI-055 tables created and rows seeded."""
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as s:
        s.add_all(
            [
                _BindPost(title="hello"),
                _BindPost(title="world"),
                _BindArticle(slug="welcome", body="Welcome to Arvel."),
                _BindArticle(slug="parity", body="Laravel-style binding."),
            ]
        )
        await s.commit()

    try:
        yield maker
    finally:
        await engine.dispose()


# ─────────────────────────── Unit tests: binder API ─────────────────────────


class TestImplicitBinderPublicAPI:
    """The implicit binder must be importable and inspectable by users."""

    def test_binder_class_is_exported(self) -> None:
        from arvel.routing import ImplicitRouteModelBinder

        assert inspect.isclass(ImplicitRouteModelBinder)

    def test_binder_detects_model_parameters(self) -> None:
        from arvel.routing import ImplicitRouteModelBinder

        async def handler(post: _BindPost) -> dict[str, Any]:
            return {"id": post.id}

        binder = ImplicitRouteModelBinder()
        params = binder.model_parameters(handler)
        assert params == {"post": _BindPost}

    def test_binder_ignores_non_model_parameters(self) -> None:
        from arvel.routing import ImplicitRouteModelBinder

        async def handler(post: _BindPost, page: int = 1) -> dict[str, Any]:
            return {"id": post.id, "page": page}

        binder = ImplicitRouteModelBinder()
        params = binder.model_parameters(handler)
        assert "page" not in params
        assert params == {"post": _BindPost}

    def test_binder_handles_string_annotations(self) -> None:
        """Handlers under ``from __future__ import annotations`` have str annotations."""
        from arvel.routing import ImplicitRouteModelBinder

        async def handler(article: _BindArticle) -> dict[str, Any]:
            return {"slug": article.slug}

        binder = ImplicitRouteModelBinder()
        params = binder.model_parameters(
            handler,
            caller_locals={"_BindArticle": _BindArticle},
        )
        assert params == {"article": _BindArticle}


# ─────────────────────── Integration: implicit binding ──────────────────────


@pytest.mark.usefixtures("bind_db")
class TestImplicitBindingIntegration:
    """Routes with ``param: Model`` annotations resolve from the DB at request time."""

    def _make_app(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        handler: Any,
        *,
        path: str,
        method: str = "GET",
    ) -> Any:
        from arvel.http.exceptions import HttpExceptionHandler
        from arvel.routing import Route, Router
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        Router.reset_singleton()

        # Per-route middleware: DatabaseTransaction binds the active session
        # so Model.find() works inside the handler.
        tx = DatabaseTransaction(session_maker=session_maker)
        getattr(Route, method.lower())(path, middleware=[tx])(handler)

        app = FastAPI()
        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)
        return TestClient(app)

    def test_pk_resolution_returns_loaded_model(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        async def show(post: _BindPost) -> dict[str, Any]:
            return {"id": post.id, "title": post.title}

        client = self._make_app(bind_db, show, path="/posts/{post}")
        resp = client.get("/posts/1")
        assert resp.status_code == 200
        assert resp.json() == {"id": 1, "title": "hello"}

    def test_missing_pk_returns_404(self, bind_db: async_sessionmaker[AsyncSession]) -> None:
        async def show(post: _BindPost) -> dict[str, Any]:
            return {"id": post.id}

        client = self._make_app(bind_db, show, path="/posts/{post}")
        resp = client.get("/posts/9999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "NOT_FOUND"

    def test_route_key_name_uses_custom_column(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        async def show(article: _BindArticle) -> dict[str, Any]:
            return {"slug": article.slug, "body": article.body}

        client = self._make_app(bind_db, show, path="/articles/{article}")
        resp = client.get("/articles/welcome")
        assert resp.status_code == 200
        assert resp.json() == {"slug": "welcome", "body": "Welcome to Arvel."}

    def test_route_key_name_404_on_missing_slug(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        async def show(article: _BindArticle) -> dict[str, Any]:
            return {"slug": article.slug}

        client = self._make_app(bind_db, show, path="/articles/{article}")
        resp = client.get("/articles/does-not-exist")
        assert resp.status_code == 404

    def test_non_model_params_pass_through_as_query(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        """Mixed handler: a model param + a regular int query param."""

        async def show(post: _BindPost, page: int = 1) -> dict[str, Any]:
            return {"id": post.id, "page": page}

        client = self._make_app(bind_db, show, path="/posts/{post}")
        resp = client.get("/posts/2?page=7")
        assert resp.status_code == 200
        assert resp.json() == {"id": 2, "page": 7}

    def test_two_model_params_in_one_handler(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        async def show(post: _BindPost, article: _BindArticle) -> dict[str, Any]:
            return {"post_id": post.id, "article_slug": article.slug}

        client = self._make_app(bind_db, show, path="/posts/{post}/articles/{article}")
        resp = client.get("/posts/1/articles/parity")
        assert resp.status_code == 200
        assert resp.json() == {"post_id": 1, "article_slug": "parity"}


# ─────────────────────── Composition with FormRequest ───────────────────────


@pytest.mark.usefixtures("bind_db")
def test_implicit_binding_coexists_with_form_request(
    bind_db: async_sessionmaker[AsyncSession],
) -> None:
    """A handler can take both an implicitly-bound model and a FormRequest body."""
    from arvel.http.requests import FormRequest
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from pydantic import BaseModel as _Pyd
    from starlette.requests import Request
    from starlette.testclient import TestClient

    class _UpdatePayload(_Pyd):
        title: str

    class _UpdateRequest(FormRequest[_UpdatePayload]):
        async def authorize(self, request: Request) -> bool:
            del request
            return True

    Router.reset_singleton()

    tx = DatabaseTransaction(session_maker=bind_db)

    @Route.put("/posts/{post}", middleware=[tx])
    async def update(post: _BindPost, body: _UpdateRequest) -> dict[str, Any]:
        return {"id": post.id, "new_title": body.validated().title}

    del update

    app = FastAPI()
    Router.singleton().register_with_app(app)
    client = TestClient(app)

    resp = client.put("/posts/1", json={"title": "fresh"})
    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "new_title": "fresh"}


# ─────────────────────── Stacking with middleware ───────────────────────────


@pytest.mark.usefixtures("bind_db")
def test_implicit_binding_runs_inside_route_middleware(
    bind_db: async_sessionmaker[AsyncSession],
) -> None:
    """Per-route Arvel middleware sees the request before model resolution; the
    handler still gets a fully-loaded model instance."""
    from collections.abc import Awaitable, Callable

    from arvel.http.middleware import Middleware
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.requests import Request
    from starlette.testclient import TestClient

    seen: list[str] = []

    class _Tag(Middleware):
        async def handle(
            self, request: Request, call_next: Callable[[Request], Awaitable[Any]]
        ) -> Any:
            seen.append(request.url.path)
            return await call_next(request)

    Router.reset_singleton()

    tx = DatabaseTransaction(session_maker=bind_db)

    @Route.get("/posts/{post}", middleware=[tx, _Tag()])
    async def show(post: _BindPost) -> dict[str, Any]:
        return {"id": post.id}

    del show

    app = FastAPI()
    Router.singleton().register_with_app(app)
    client = TestClient(app)

    resp = client.get("/posts/1")
    assert resp.status_code == 200
    assert resp.json() == {"id": 1}
    assert seen == ["/posts/1"]
