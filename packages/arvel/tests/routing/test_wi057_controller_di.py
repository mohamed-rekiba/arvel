"""Method-based controller routing with DI.

(controller DI). The invokable case lives in
``test_043_critical_fixes.py``; here we cover the multi-action shape:

    Route.get("/users/{id}", controller=UserController, action="show")

The framework must:
  1. Resolve ``UserController`` through ``app.state.arvel_container`` (DI).
  2. Bind to the named method, preserving its signature so FastAPI can wire
     path/query/body params normally.
  3. Coexist with implicit route model binding and ``FormRequest``.

Run BEFORE implementation — every test in this file MUST fail (RED state).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from arvel.container import Container
from arvel.database import Model, id_, string
from arvel.http.controller import Controller
from arvel.http.middleware.database_transaction import DatabaseTransaction
from arvel.http.requests import FormRequest
from arvel.routing import Route, Router
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class _WidgetCtrlModel(Model):
    """Tiny Model so route model binding has something to chew on."""

    __tablename__ = "wi057_widget_ctrl"

    id: int = id_()
    name: str = string(80)


@pytest_asyncio.fixture
async def bind_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Per-test engine with the table created and rows seeded."""
    engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as s:
        s.add_all([_WidgetCtrlModel(name="alpha"), _WidgetCtrlModel(name="beta")])
        await s.commit()

    try:
        yield maker
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def reset_router() -> None:
    Router.reset_singleton()


# Unit tests: action=


class TestActionParameter:
    """``action=`` lets you bind any method on a controller class."""

    def test_action_kwarg_is_accepted_by_route_decorators(self) -> None:
        class Ctrl(Controller):
            async def show(self) -> dict[str, str]:
                return {"hit": "show"}

        Route.get("/ctrl/show", controller=Ctrl, action="show")

        specs = Router.singleton().routes()
        assert len(specs) == 1
        assert specs[0].controller is Ctrl
        assert specs[0].action == "show"

    def test_action_routes_to_named_method(self) -> None:
        class MultiCtrl(Controller):
            async def index(self) -> dict[str, str]:
                return {"hit": "index"}

            async def show(self) -> dict[str, str]:
                return {"hit": "show"}

        Route.get("/multi/idx", controller=MultiCtrl, action="index")
        Route.get("/multi/show", controller=MultiCtrl, action="show")

        app = FastAPI()
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        assert client.get("/multi/idx").json() == {"hit": "index"}
        assert client.get("/multi/show").json() == {"hit": "show"}

    def test_missing_action_and_call_is_a_clear_error(self) -> None:
        """A controller class without __call__ or action= fails loudly at decoration time."""

        class BrokenCtrl(Controller):
            async def index(self) -> dict[str, str]:
                return {"hit": "index"}

        with pytest.raises(TypeError, match="action="):
            Route.get("/broken", controller=BrokenCtrl)


# DI through container


class TestMethodControllerDI:
    """Constructor dependencies are resolved through the container."""

    def test_method_controller_with_dependency_gets_injected(self) -> None:
        class GreetService:
            def greet(self) -> str:
                return "hello"

        class GreetController(Controller):
            def __init__(self, svc: GreetService) -> None:
                self.svc = svc

            async def hello(self) -> dict[str, str]:
                return {"msg": self.svc.greet()}

        Route.get("/greet", controller=GreetController, action="hello")

        app = FastAPI()
        container = Container()
        container.bind(GreetService)
        app.state.arvel_container = container
        Router.singleton().register_with_app(app)

        resp = TestClient(app).get("/greet")
        assert resp.status_code == 200
        assert resp.json() == {"msg": "hello"}

    def test_method_controller_singleton_dependency_is_shared(self) -> None:
        class Repo:
            def __init__(self) -> None:
                self.token = "shared"

        class ACtrl(Controller):
            def __init__(self, repo: Repo) -> None:
                self.repo = repo

            async def show(self) -> dict[str, str]:
                return {"src": "A", "tok": self.repo.token}

        class BCtrl(Controller):
            def __init__(self, repo: Repo) -> None:
                self.repo = repo

            async def show(self) -> dict[str, str]:
                return {"src": "B", "tok": self.repo.token}

        Route.get("/a", controller=ACtrl, action="show")
        Route.get("/b", controller=BCtrl, action="show")

        app = FastAPI()
        container = Container()
        container.singleton(Repo)
        app.state.arvel_container = container
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        assert client.get("/a").json() == {"src": "A", "tok": "shared"}
        assert client.get("/b").json() == {"src": "B", "tok": "shared"}

    def test_zero_arg_method_controller_works_without_container(self) -> None:
        """No container, no constructor deps — must still mount cleanly."""

        class PingCtrl(Controller):
            async def ping(self) -> dict[str, str]:
                return {"pong": "ok"}

        Route.get("/ping", controller=PingCtrl, action="ping")

        app = FastAPI()
        Router.singleton().register_with_app(app)

        resp = TestClient(app).get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"pong": "ok"}


# Signature flows through


class TestMethodControllerSignature:
    """The bound method's signature must flow through to FastAPI."""

    def test_method_controller_receives_path_params(self) -> None:
        class Ctrl(Controller):
            async def show(self, widget_id: int) -> dict[str, int]:
                return {"id": widget_id}

        Route.get("/widgets/{widget_id}", controller=Ctrl, action="show")

        app = FastAPI()
        Router.singleton().register_with_app(app)

        resp = TestClient(app).get("/widgets/42")
        assert resp.status_code == 200
        assert resp.json() == {"id": 42}

    def test_method_controller_supports_sync_methods(self) -> None:
        class Ctrl(Controller):
            def info(self) -> dict[str, str]:
                return {"sync": "yes"}

        Route.get("/info", controller=Ctrl, action="info")

        app = FastAPI()
        Router.singleton().register_with_app(app)

        resp = TestClient(app).get("/info")
        assert resp.status_code == 200
        assert resp.json() == {"sync": "yes"}


# Integrations


@pytest.mark.usefixtures("bind_db")
class TestMethodControllerIntegrations:
    """Controllers must compose with the rest of the routing pipeline."""

    def test_method_controller_with_implicit_model_binding(
        self, bind_db: async_sessionmaker[AsyncSession]
    ) -> None:
        class WidgetCtrl(Controller):
            async def show(self, widget: _WidgetCtrlModel) -> dict[str, Any]:
                return {"id": widget.id, "name": widget.name}

        tx = DatabaseTransaction(session_maker=bind_db)
        Route.get("/widgets/{widget}", controller=WidgetCtrl, action="show", middleware=[tx])

        app = FastAPI()
        from arvel.http.exceptions import HttpExceptionHandler

        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)

        client = TestClient(app)
        assert client.get("/widgets/1").json() == {"id": 1, "name": "alpha"}
        assert client.get("/widgets/2").json() == {"id": 2, "name": "beta"}
        assert client.get("/widgets/999").status_code == 404

    def test_method_controller_with_form_request(self) -> None:
        class _CreatePayload(BaseModel):
            name: str

        class _CreateRequest(FormRequest[_CreatePayload]):
            async def authorize(self, request: Any) -> bool:
                del request
                return True

        class WidgetCtrl(Controller):
            async def store(self, body: _CreateRequest) -> dict[str, str]:
                return {"name": body.validated().name}

        Route.post("/widgets", controller=WidgetCtrl, action="store")

        app = FastAPI()
        Router.singleton().register_with_app(app)

        resp = TestClient(app).post("/widgets", json={"name": "gamma"})
        assert resp.status_code == 200
        assert resp.json() == {"name": "gamma"}


# Public adapter API


class TestAdapterPublicAPI:
    """Public adapter is importable and callable."""

    def test_method_controller_adapter_is_exported(self) -> None:
        from arvel import routing

        assert hasattr(routing, "MethodControllerAdapter")

    def test_method_controller_adapter_resolves_method_on_instance(self) -> None:
        from arvel.routing import MethodControllerAdapter

        class Ctrl(Controller):
            def __init__(self) -> None:
                self.calls = 0

            async def ping(self) -> dict[str, int]:
                self.calls += 1
                return {"calls": self.calls}

        handler = MethodControllerAdapter(Ctrl, "ping").build()

        async def _run() -> Any:
            return await handler()

        assert asyncio.run(_run()) == {"calls": 1}
