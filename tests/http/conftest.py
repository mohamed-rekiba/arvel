"""HTTP test fixtures.

Provides pre-built ASGI apps with various middleware/controller configurations
for the HTTP layer test suite. These fixtures build real FastAPI apps with
Arvel's HTTP layer wired in, so tests exercise the full request path.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI, Request  # noqa: TC002
from pydantic import BaseModel
from starlette.responses import JSONResponse

from arvel.foundation.container import ContainerBuilder
from arvel.foundation.container import Scope as DIScope

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.types import ASGIApp, Receive, Scope, Send

# ── Shared test models ──


class CreateItemRequest(BaseModel):
    name: str
    price: float


# ── Shared test service ──


class FakeItemService:
    """A simple service to verify DI works."""

    def __init__(self) -> None:
        self.injected = True

    async def list_items(self) -> list[dict]:
        return [{"id": 1, "name": "Widget"}]

    async def get_item(self, item_id: int) -> dict:
        return {"id": item_id, "name": "Widget"}

    async def create_item(self, name: str, price: float) -> dict:
        return {"name": name, "price": price}


# ── Scoped service for FR-035 ──


class ScopedService:
    def __init__(self) -> None:
        self.instance_id = str(uuid.uuid4())


# ── Middleware helpers ──


def make_logging_middleware(name: str, log: list[str]):
    """Create a pure ASGI middleware that logs before/after."""

    class LogMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                log.append(f"{name}_before")
            await self.app(scope, receive, send)
            if scope["type"] == "http":
                log.append(f"{name}_after")

    LogMiddleware.__name__ = f"LogMiddleware_{name}"
    LogMiddleware.__qualname__ = f"LogMiddleware_{name}"
    return LogMiddleware


def make_blocking_middleware(log: list[str]):
    """Middleware that returns 403 without calling next."""

    class BlockingMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                log.append("blocked")
                response = JSONResponse({"error": "forbidden"}, status_code=403)
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)

    return BlockingMiddleware


def make_crashing_middleware():
    """Middleware that always raises an exception."""

    class CrashingMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            raise RuntimeError("middleware explosion")

    return CrashingMiddleware


def make_terminable_middleware(log: list[str]):
    """Middleware with a terminate() hook."""

    class TerminableMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            await self.app(scope, receive, send)
            if scope["type"] == "http":
                await self.terminate()

        async def terminate(self) -> None:
            log.append("terminate")

    return TerminableMiddleware


# ── Fixtures ──


@pytest.fixture
def http_app_basic() -> FastAPI:
    """Minimal FastAPI app with Arvel exception handler."""
    from arvel.http.exception_handler import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app, debug=False)
    return app


@pytest.fixture
def http_app_with_middleware() -> tuple[FastAPI, list[str]]:
    """App with two global middleware ordered by priority."""
    from arvel.http.exception_handler import install_exception_handlers
    from arvel.http.kernel import HttpKernel

    log: list[str] = []
    app = FastAPI()
    install_exception_handlers(app, debug=False)

    mw_10 = make_logging_middleware("global_10", log)
    mw_20 = make_logging_middleware("global_20", log)

    kernel = HttpKernel()
    kernel.add_global_middleware(mw_10, priority=10)
    kernel.add_global_middleware(mw_20, priority=20)
    kernel.mount(app)

    @app.get("/test")
    async def test_handler() -> dict:
        return {"ok": True}

    return app, log


@pytest.fixture
def http_app_with_route_middleware() -> tuple[FastAPI, list[str]]:
    """App with global + route-level middleware."""
    from arvel.http.exception_handler import install_exception_handlers
    from arvel.http.kernel import HttpKernel

    log: list[str] = []
    app = FastAPI()
    install_exception_handlers(app, debug=False)

    global_mw = make_logging_middleware("global", log)
    route_mw = make_logging_middleware("route", log)

    kernel = HttpKernel()
    kernel.add_global_middleware(global_mw, priority=10)
    app.add_middleware(route_mw)
    kernel.mount(app)

    @app.get("/protected")
    async def protected_handler() -> dict:
        return {"protected": True}

    return app, log


@pytest.fixture
def http_app_with_blocking_middleware() -> tuple[FastAPI, list[str]]:
    """App with middleware that blocks (doesn't call next)."""
    from arvel.http.exception_handler import install_exception_handlers
    from arvel.http.kernel import HttpKernel

    log: list[str] = []
    app = FastAPI()
    install_exception_handlers(app, debug=False)

    blocking = make_blocking_middleware(log)

    kernel = HttpKernel()
    kernel.add_global_middleware(blocking, priority=10)
    kernel.mount(app)

    @app.get("/blocked")
    async def blocked_handler() -> dict:
        log.append("handler")
        return {"reached": True}

    return app, log


@pytest.fixture
def http_app_with_terminable_middleware() -> tuple[FastAPI, list[str]]:
    """App with terminable middleware."""
    from arvel.http.exception_handler import install_exception_handlers
    from arvel.http.kernel import HttpKernel

    log: list[str] = []
    app = FastAPI()
    install_exception_handlers(app, debug=False)

    terminable = make_terminable_middleware(log)

    kernel = HttpKernel()
    kernel.add_global_middleware(terminable, priority=10)
    kernel.mount(app)

    @app.get("/test")
    async def test_handler() -> dict:
        return {"ok": True}

    return app, log


@pytest.fixture
def http_app_with_crashing_middleware() -> FastAPI:
    """App with middleware that crashes."""
    from arvel.http.exception_handler import install_exception_handlers
    from arvel.http.kernel import HttpKernel

    app = FastAPI()
    install_exception_handlers(app, debug=False)

    crashing = make_crashing_middleware()

    kernel = HttpKernel()
    kernel.add_global_middleware(crashing, priority=10)
    kernel.mount(app)

    @app.get("/test")
    async def test_handler() -> dict:
        return {"ok": True}

    return app


@pytest.fixture
def http_app_with_enforced_global() -> tuple[FastAPI, list[str]]:
    """App verifying global middleware always runs even on routes without explicit middleware."""
    from arvel.http.exception_handler import install_exception_handlers
    from arvel.http.kernel import HttpKernel

    log: list[str] = []
    app = FastAPI()
    install_exception_handlers(app, debug=False)

    security_mw = make_logging_middleware("global_security", log)

    kernel = HttpKernel()
    kernel.add_global_middleware(security_mw, priority=1)
    kernel.mount(app)

    @app.get("/route-without-explicit-middleware")
    async def plain_handler() -> dict:
        return {"ok": True}

    return app, log


@pytest.fixture
def http_app_with_controller() -> FastAPI:
    """App with a controller that uses DI for service injection."""
    from arvel.http.controller import resolve_controller
    from arvel.http.exception_handler import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app, debug=False)

    builder = ContainerBuilder()
    builder.provide(FakeItemService, FakeItemService, scope=DIScope.REQUEST)
    builder.build()

    @app.get("/items")
    async def list_items(
        service: FakeItemService = resolve_controller(FakeItemService),  # noqa: B008
    ) -> dict:
        return {"service_injected": service.injected}

    @app.get("/items/{item_id}")
    async def get_item(item_id: int) -> dict:
        return {"item_id": item_id}

    @app.post("/items", status_code=201)
    async def create_item(body: CreateItemRequest) -> dict:
        return {"name": body.name, "price": body.price}

    @app.get("/request-info")
    async def request_info(request: Request) -> dict:
        return {"method": request.method, "url": str(request.url)}

    return app


@pytest.fixture
def http_app_with_scoped_service() -> Any:
    """App with REQUEST-scoped service to verify per-request isolation."""
    from arvel.http.exception_handler import install_exception_handlers
    from arvel.http.request import RequestContainerMiddleware

    close_log: list[str] = []
    app = FastAPI()
    install_exception_handlers(app, debug=False)

    builder = ContainerBuilder()
    builder.provide(ScopedService, ScopedService, scope=DIScope.REQUEST)
    container = builder.build()

    # Install request container middleware
    RequestContainerMiddleware.install(app, container, on_close=lambda: close_log.append("closed"))

    @app.get("/scoped-id")
    async def scoped_id(request: Request) -> dict:
        req_container = request.state.container
        svc = await req_container.resolve(ScopedService)
        return {"instance_id": svc.instance_id}

    return app, close_log


@pytest.fixture
def http_app_with_crashing_handler() -> FastAPI:
    """App with a handler that raises an unhandled exception."""
    from arvel.http.exception_handler import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app, debug=False)

    @app.get("/crash")
    async def crash() -> dict:
        raise RuntimeError("unhandled boom")

    return app


@pytest.fixture
def http_app_production_mode() -> FastAPI:
    """App in production mode (debug=False) with crashing handler."""
    from arvel.http.exception_handler import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app, debug=False)

    @app.get("/crash")
    async def crash() -> dict:
        raise RuntimeError("secret internal error with /path/to/file.py")

    return app


@pytest.fixture
def http_app_debug_mode() -> FastAPI:
    """App in debug mode (debug=True) with crashing handler."""
    from arvel.http.exception_handler import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app, debug=True)

    @app.get("/crash")
    async def crash() -> dict:
        raise RuntimeError("debug error details")

    return app


@pytest.fixture
def tmp_project_with_http_module(tmp_project: Path) -> Path:
    """Project with bootstrap providers and routes/items.py for integration tests."""
    (tmp_project / "bootstrap" / "providers.py").write_text(
        "from arvel.foundation.provider import ServiceProvider\n\n"
        "class ItemsProvider(ServiceProvider):\n"
        "    async def register(self, container):\n"
        "        pass\n\n"
        "    async def boot(self, app):\n"
        "        pass\n\n"
        "providers = [ItemsProvider]\n"
    )
    routes_dir = tmp_project / "routes"
    routes_dir.mkdir(exist_ok=True)
    (routes_dir / "items.py").write_text(
        "from arvel.http.router import Router\n\n"
        "router = Router()\n\n"
        "router.get('/test-items', lambda: {'items': []}, name='items.index')\n"
    )
    return tmp_project
