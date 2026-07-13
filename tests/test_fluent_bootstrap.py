"""Fluent bootstrap: the builder loads providers/middleware from
Python files, applies a custom config dir, and `with_routing(web=, api=)` imports route files inside
their kernel middleware group (api also URL-prefixed `/api`); `console` is not an HTTP route file."""

from __future__ import annotations

from pathlib import Path

from arvel.kernel.application import Application
from arvel.kernel.bootstrap import load_route_files
from arvel.kernel.globals import set_application
from arvel.kernel.service_provider import load_config_directory
from arvel.routing import Router


def test_with_config_dir_loads_from_a_custom_directory(tmp_path: Path) -> None:
    cfg = tmp_path / "settings"
    cfg.mkdir()
    (cfg / "app.py").write_text("config = {'name': 'Custom'}\n")
    app = Application.configure(str(tmp_path)).with_config_dir(cfg).create()
    assert app.config_dir == str(cfg)
    load_config_directory(app, app.config_dir)
    assert app.config("app.name") == "Custom"


def test_with_providers_loads_a_providers_file(tmp_path: Path) -> None:
    (tmp_path / "providers.py").write_text(
        "from arvel.kernel import ServiceProvider\n\n"
        "class AppServiceProvider(ServiceProvider):\n"
        "    def register(self) -> None:\n"
        "        self.app.instance('marker', 42)\n\n"
        "providers = [AppServiceProvider]\n"
    )
    app = Application.configure(str(tmp_path)).with_providers(tmp_path / "providers.py").create()
    assert app.make("marker") == 42  # the file's provider was registered


def test_with_middlewares_loads_a_middleware_file(tmp_path: Path) -> None:
    """with_middlewares([...]) must actually run on the served app — verified through the real
    ASGI serve path, not a fake kernel binding (which previously masked that middlewares were dropped)."""
    from litestar.testing import TestClient

    (tmp_path / "middlewares.py").write_text(
        "from arvel.http.middleware import Middleware\n"
        "from arvel.http.exceptions import abort\n\n"
        "class ShortCircuit(Middleware):\n"
        "    async def handle(self, request, call_next):\n"
        "        if request.header('x-trip-mw') == 'yes':\n"
        "            abort(418, 'mw ran')\n"
        "        return await call_next(request)\n\n"
        "middlewares = [ShortCircuit]\n"
    )
    (tmp_path / "web.py").write_text(
        "from arvel.support.facades import Route\n\n"
        "async def home() -> str: return 'home'\n\n"
        "Route.get('/', home, name='home')\n"
    )
    app = (
        Application.configure(str(tmp_path))
        .with_middlewares(tmp_path / "middlewares.py")
        .with_routing(web=tmp_path / "web.py")
        .create()
    )
    with TestClient(app=app.as_asgi()) as client:
        assert client.get("/").status_code == 200  # passes through normally
        tripped = client.get(  # the builder middleware short-circuits this one
            "/", headers={"x-trip-mw": "yes", "accept": "application/json"}
        )
    assert tripped.status_code == 418  # the builder middleware ran on the real served path
    assert tripped.json()["message"] == "mw ran"


def test_with_routing_imports_web_and_api_inside_their_groups(tmp_path: Path) -> None:
    (tmp_path / "web.py").write_text(
        "from arvel.support.facades import Route\n\n"
        "async def home() -> str: return 'home'\n\n"
        "Route.get('/', home, name='home')\n"
    )
    (tmp_path / "api.py").write_text(
        "from arvel.support.facades import Route\n\n"
        "async def users() -> list[str]: return []\n\n"
        "Route.get('/users', users, name='users.index')\n"
    )
    app = Application(base_path=str(tmp_path))
    app.instance("router", Router())
    app.routing = {"web": "web.py", "api": "api.py", "console": "console.py"}
    set_application(app)
    try:
        load_route_files(app)
    finally:
        set_application(None)

    routes = {r.name: r for r in app.make("router").routes()}
    # web → "web" group, no prefix
    assert routes["home"].group == "web"
    assert routes["home"].path == "/"
    # api → "api" group, URL-prefixed /api
    assert (
        routes["api.users.index" if "api.users.index" in routes else "users.index"].group == "api"
    )
    assert routes["users.index"].path == "/api/users"
    # console is a CLI-command file, not HTTP — it must not register HTTP routes
    assert not any(r.path.startswith("/console") for r in app.make("router").routes())
