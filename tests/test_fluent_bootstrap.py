"""Fluent bootstrap (Laravel-style `bootstrap/app.py`): the builder loads providers/middleware from
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


async def test_with_middlewares_loads_a_middleware_file(tmp_path: Path) -> None:
    (tmp_path / "middlewares.py").write_text(
        "class AuthMiddleware: ...\n\nmiddlewares = [AuthMiddleware]\n"
    )
    app = (
        Application.configure(str(tmp_path)).with_middlewares(tmp_path / "middlewares.py").create()
    )

    class Kernel:
        def __init__(self) -> None:
            self.global_middleware: list[object] = []

        def resolve_middleware(self, ref: object) -> object:
            return ref

    kernel = Kernel()
    app.instance("http", kernel)
    await app.boot()
    # the file's `middlewares = [...]` list appended to the kernel's global stack
    assert [
        type(m).__name__ if not isinstance(m, type) else m.__name__
        for m in kernel.global_middleware
    ] == ["AuthMiddleware"]


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
