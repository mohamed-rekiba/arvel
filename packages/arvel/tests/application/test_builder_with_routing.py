"""``ApplicationBuilder.with_routing(web=, api=, console=)``.

The builder accepts up to three optional route file paths. ``web`` and
``api`` are loaded by ``HttpServiceProvider.register()`` at create-time;
``console`` is stored on the application but NOT loaded in (no
Console provider exists yet — wired here so can pick it up
without a builder API change).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel import Application
from starlette.routing import Route as StarletteRoute


def _make_routes_dir(tmp_path: Path) -> Path:
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.py").write_text(
        "# Skeleton route file — populated in Stage 3b.\n",
    )
    (routes / "api.py").write_text("# api routes\n")
    (routes / "console.py").write_text("# console routes\n")
    return routes


def test_with_routing_accepts_web_only(tmp_path: Path) -> None:
    routes = _make_routes_dir(tmp_path)
    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_routing(web=routes / "web.py")
    )
    assert builder is not None


def test_with_routing_accepts_api_only(tmp_path: Path) -> None:
    routes = _make_routes_dir(tmp_path)
    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_routing(api=routes / "api.py")
    )
    assert builder is not None


def test_with_routing_accepts_all_three(tmp_path: Path) -> None:
    routes = _make_routes_dir(tmp_path)
    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_routing(
            web=routes / "web.py",
            api=routes / "api.py",
            console=routes / "console.py",
        )
    )
    assert builder is not None


def test_with_routing_accepts_str_path(tmp_path: Path) -> None:
    routes = _make_routes_dir(tmp_path)
    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_routing(web=str(routes / "web.py"))
    )
    assert builder is not None


def test_with_routing_requires_at_least_one_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="with_routing"):
        Application.configure(tmp_path).with_environment("testing").with_routing()


def test_with_routing_accumulates_across_calls(tmp_path: Path) -> None:
    """Calling with_routing twice with different keys accumulates (doesn't reset)."""
    routes = _make_routes_dir(tmp_path)

    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_routing(web=routes / "web.py")
        .with_routing(api=routes / "api.py")
    )

    # Internal verification: both paths are stored.
    stored = builder._routing_paths  # pyright: ignore[reportPrivateUsage]
    assert "web" in stored
    assert "api" in stored


def test_with_routing_last_write_wins_per_key(tmp_path: Path) -> None:
    """Calling with_routing twice with the same key replaces the earlier value."""
    routes = _make_routes_dir(tmp_path)
    first = routes / "web.py"
    second = tmp_path / "alt_web.py"
    second.write_text("# alternate\n")

    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_routing(web=first)
        .with_routing(web=second)
    )

    stored = builder._routing_paths  # pyright: ignore[reportPrivateUsage]
    assert stored["web"] == second


def test_with_routing_console_only_does_not_raise(tmp_path: Path) -> None:
    """Console paths are stored but not loaded in — must not error at builder call."""
    routes = _make_routes_dir(tmp_path)
    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_routing(console=routes / "console.py")
    )
    assert builder is not None


def test_with_routing_create_succeeds_when_no_routes_registered(tmp_path: Path) -> None:
    """An app that never called with_routing must still create cleanly (regression guard)."""
    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()
    assert isinstance(app, Application)


def test_with_routing_loads_web_routes_at_boot(tmp_path: Path) -> None:
    """End-to-end: a web.py declaring a route becomes reachable on the FastAPI app.

    This test fails today (with_routing raises NotImplementedError at .create()).
    Stage 3b will make it green.
    """
    pytest.importorskip("fastapi")
    from arvel import HttpServiceProvider

    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.py").write_text(
        "from arvel import Route\n"
        "\n"
        "@Route.get('/hello')\n"
        "async def hello() -> dict[str, str]:\n"
        "    return {'msg': 'hi'}\n",
    )

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([HttpServiceProvider])
        .with_routing(web=routes / "web.py")
        .create()
    )

    asgi = app.into_asgi()
    # Verify the route is mounted on the FastAPI app.
    routes_on_app = [r.path for r in asgi.routes if isinstance(r, StarletteRoute)]
    assert "/hello" in routes_on_app


def test_with_routing_missing_path_raises_at_create(tmp_path: Path) -> None:
    """A registered routing path that doesn't exist on disk raises at .create()."""
    missing = tmp_path / "routes" / "web.py"  # parent doesn't exist

    builder = Application.configure(tmp_path).with_environment("testing").with_routing(web=missing)

    with pytest.raises((FileNotFoundError, RuntimeError)):
        builder.create()
