"""`Application.configure(...).with_public_dir(...)`: RoutingServiceProvider registers Route.public()
automatically at boot when a public dir is configured — no route-file code needed, same as the public/."""

from __future__ import annotations

from pathlib import Path

from litestar.testing import TestClient

from arvel.kernel.application import Application
from arvel.kernel.bootstrap import bootstrap_app


def _build_public_dir(tmp_path: Path) -> Path:
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text("<html>shell</html>")
    (public / "favicon.ico").write_text("ico")
    return public


def test_with_public_dir_serves_real_files_with_no_route_file(tmp_path: Path) -> None:
    public = _build_public_dir(tmp_path)
    app = Application.configure(str(tmp_path)).with_public_dir(public).create()
    bootstrap_app(app)  # the real sync boot sequence — no routes/web.py involved at all

    with TestClient(app=app.as_asgi()) as client:
        resp = client.get("/favicon.ico")
        assert resp.is_success
        assert resp.text == "ico"


def test_with_public_dir_falls_back_to_index_html(tmp_path: Path) -> None:
    public = _build_public_dir(tmp_path)
    app = Application.configure(str(tmp_path)).with_public_dir(public).create()
    bootstrap_app(app)

    with TestClient(app=app.as_asgi()) as client:
        resp = client.get("/some/deep/link")
        assert resp.is_success
        assert resp.text == "<html>shell</html>"


def test_with_public_dir_accepts_a_sub_path(tmp_path: Path) -> None:
    """with_public_dir(directory, path="/app") mounts under a sub-path instead of the root — the
    same `path` param Router.public() itself takes."""
    public = _build_public_dir(tmp_path)
    app = Application.configure(str(tmp_path)).with_public_dir(public, path="/app").create()
    bootstrap_app(app)

    with TestClient(app=app.as_asgi()) as client:
        resp = client.get("/app/favicon.ico")
        assert resp.is_success
        assert resp.text == "ico"

        resp = client.get("/app/some/deep/link")
        assert resp.is_success
        assert resp.text == "<html>shell</html>"

        # outside the mounted sub-path, nothing is registered
        resp = client.get("/favicon.ico")
        assert resp.status_code == 404


def test_with_public_dir_spa_fallback_false_serves_static_only(tmp_path: Path) -> None:
    """with_public_dir(spa_fallback=False): only real files are served, unmatched paths 404, and the
    root isn't claimed — the app's own "/" route stays reachable."""
    public = _build_public_dir(tmp_path)

    web_routes = tmp_path / "web.py"
    web_routes.write_text(
        "from arvel import Route\n\n"
        "async def home(request):\n"
        "    return {'ok': True}\n\n"
        "Route.get('/', home, name='home')\n"
    )
    app = (
        Application.configure(str(tmp_path))
        .with_public_dir(public, spa_fallback=False)
        .with_routing(web=web_routes)
        .create()
    )
    bootstrap_app(app)

    with TestClient(app=app.as_asgi()) as client:
        # the app's own "/" route is reachable — with_public_dir never claimed it
        resp = client.get("/")
        assert resp.json() == {"ok": True}

        # a real file still serves
        resp = client.get("/favicon.ico")
        assert resp.is_success
        assert resp.text == "ico"

        # an unmatched path 404s — no SPA shell fallback
        resp = client.get("/some/deep/link")
        assert resp.status_code == 404


def test_coexists_with_real_routes_registered_via_with_routing_web(tmp_path: Path) -> None:
    """A real routes/web.py can still register specific routes alongside the auto-registered public()
    fallback — is_fallback sorting means a specific route always wins, regardless of registration order."""
    public = _build_public_dir(tmp_path)
    web_routes = tmp_path / "web.py"
    web_routes.write_text(
        "from arvel import Route\n\n"
        "async def hello(request):\n"
        "    return {'hello': 'world'}\n\n"
        "Route.get('/hello', hello, name='hello')\n"
    )
    app = (
        Application.configure(str(tmp_path))
        .with_public_dir(public)
        .with_routing(web=web_routes)
        .create()
    )
    bootstrap_app(app)  # register() (auto public()) runs, THEN load_route_files() imports web.py

    with TestClient(app=app.as_asgi()) as client:
        # the real route from routes/web.py wins on its own specific path
        resp = client.get("/hello")
        assert resp.json() == {"hello": "world"}

        # everything else is still covered by the auto-registered public() fallback
        resp = client.get("/favicon.ico")
        assert resp.is_success
        assert resp.text == "ico"

        resp = client.get("/some/other/path")
        assert resp.is_success
        assert resp.text == "<html>shell</html>"


def test_without_with_public_dir_nothing_is_registered(tmp_path: Path) -> None:
    """No `with_public_dir(...)` call → app.public_dir stays None → no auto-registered routes —
    confirms this is opt-in, not something every app pays for."""
    app = Application.configure(str(tmp_path)).create()
    bootstrap_app(app)
    assert app.public_dir is None

    with TestClient(app=app.as_asgi()) as client:
        resp = client.get("/")
        assert resp.status_code == 404
