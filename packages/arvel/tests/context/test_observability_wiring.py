"""Epic 001 Story 3 — observability auto-wiring and startup route logging."""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel.application import Application
from arvel.context import ContextMiddleware, DeferredTaskMiddleware
from arvel.http.middleware.scope import ArvelScopeMiddleware
from arvel.observability import ObservabilityMiddleware, ObservabilityServiceProvider
from fastapi import FastAPI


def _middleware_classes(app: FastAPI) -> list[object]:
    return [m.cls for m in app.user_middleware]


def test_into_asgi_mounts_observability_middleware_without_config(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()

    asgi = app.into_asgi()
    classes = _middleware_classes(asgi)

    assert ObservabilityMiddleware in classes
    assert ContextMiddleware in classes
    assert DeferredTaskMiddleware in classes
    assert ArvelScopeMiddleware in classes


def test_middleware_stack_order_outer_to_inner(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()

    asgi = app.into_asgi()
    classes = _middleware_classes(asgi)

    # add_middleware prepends, so user_middleware[0] is the outermost layer.
    obs = classes.index(ObservabilityMiddleware)
    ctx = classes.index(ContextMiddleware)
    deferred = classes.index(DeferredTaskMiddleware)
    scope = classes.index(ArvelScopeMiddleware)
    assert obs < ctx < deferred < scope


def test_observability_provider_is_in_baseline(tmp_path: Path) -> None:
    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()
    provider_types = [type(p) for p in app.iter_providers()]
    assert ObservabilityServiceProvider in provider_types


def test_observability_provider_not_registered_twice(tmp_path: Path) -> None:
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([ObservabilityServiceProvider])
        .create()
    )
    provider_types = [type(p) for p in app.iter_providers()]
    assert provider_types.count(ObservabilityServiceProvider) == 1


async def test_routes_logged_at_debug_on_boot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    # Keep the SDK off so FakeObservability's logger provider survives boot.
    monkeypatch.setenv("OTEL_SDK_DISABLED", "1")
    from arvel import HttpServiceProvider
    from arvel.testing.observability import FakeObservability

    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.py").write_text(
        "from arvel import Route\n"
        "\n"
        "@Route.get('/hello', name='hello')\n"
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

    with FakeObservability() as obs:
        await app.boot()

    obs.assert_logged("route.registered", method="GET", path="/hello", name="hello")
