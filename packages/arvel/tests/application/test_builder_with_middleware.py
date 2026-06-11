"""``ApplicationBuilder.with_middleware`` — declarative global ASGI stack.

The stack is declared like ``bootstrap/providers.py``: a list of
``GlobalMiddleware`` classes (or a path to a module that exposes
``middleware = [...]``). List order is outer→inner. ``ArvelScopeMiddleware`` is
pinned innermost regardless of the list, so an edited ``bootstrap/middleware.py``
can't strand the per-request DI scope.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from arvel import Application
from arvel.context import ContextMiddleware
from arvel.http.middleware import ArvelScopeMiddleware, TrustProxiesMiddleware
from arvel.observability import ObservabilityMiddleware
from fastapi import FastAPI


def _names(fa: FastAPI) -> list[str]:
    return [getattr(mw.cls, "__name__", type(mw.cls).__name__) for mw in fa.user_middleware]


def _outer_to_inner(fa: FastAPI) -> list[str]:
    # add_middleware prepends, so user_middleware is already outer→inner.
    return _names(fa)


def test_with_middleware_list_controls_the_stack(tmp_path: Path) -> None:
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([])
        .with_middleware([ObservabilityMiddleware, ContextMiddleware])
        .create()
    )
    fa = app.into_asgi()
    names = _names(fa)

    # Only the listed middleware mount (plus the pinned ArvelScope) — the rest
    # of the default stack is gone because the user declared their own list.
    assert "ObservabilityMiddleware" in names
    assert "ContextMiddleware" in names
    assert "DeferredTaskMiddleware" not in names
    assert "ArvelScopeMiddleware" in names


def test_arvel_scope_is_pinned_innermost_even_if_omitted(tmp_path: Path) -> None:
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([])
        .with_middleware([ObservabilityMiddleware])
        .create()
    )
    fa = app.into_asgi()
    order = _outer_to_inner(fa)

    assert "ArvelScopeMiddleware" in order
    assert order[-1] == "ArvelScopeMiddleware"


def test_list_order_is_outer_to_inner(tmp_path: Path) -> None:
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([])
        # Observability declared OUTSIDE Context here (reversed vs the default).
        .with_middleware([ContextMiddleware, ObservabilityMiddleware])
        .create()
    )
    fa = app.into_asgi()
    order = _outer_to_inner(fa)

    assert order.index("ContextMiddleware") < order.index("ObservabilityMiddleware")


def test_duplicate_arvel_scope_in_list_is_deduped(tmp_path: Path) -> None:
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([])
        .with_middleware([ArvelScopeMiddleware, ObservabilityMiddleware, ArvelScopeMiddleware])
        .create()
    )
    fa = app.into_asgi()
    order = _outer_to_inner(fa)

    assert order.count("ArvelScopeMiddleware") == 1
    assert order[-1] == "ArvelScopeMiddleware"


def test_no_with_middleware_uses_framework_default_stack(tmp_path: Path) -> None:
    app = Application.configure(tmp_path).with_environment("testing").with_providers([]).create()
    fa = app.into_asgi()
    names = _names(fa)

    # The default stack still mounts the usual layers when none is declared.
    assert "ObservabilityMiddleware" in names
    assert "ContextMiddleware" in names
    assert "ArvelScopeMiddleware" in names


def test_with_middleware_loads_from_path(tmp_path: Path) -> None:
    middleware_file = tmp_path / "middleware.py"
    middleware_file.write_text(
        "from arvel.http.middleware import TrustProxiesMiddleware\n"
        "from arvel.observability import ObservabilityMiddleware\n"
        "middleware = [TrustProxiesMiddleware, ObservabilityMiddleware]\n"
    )
    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([])
        .with_middleware(middleware_file)
        .create()
    )
    # TrustProxies self-skips without TRUSTED_PROXIES; Observability mounts.
    fa = app.into_asgi()
    names = _names(fa)
    assert "ObservabilityMiddleware" in names
    assert "ArvelScopeMiddleware" in names
    # TrustProxies was listed but self-gates off (no trusted proxies configured).
    assert "TrustProxiesMiddleware" not in names


def test_with_middleware_path_missing_attribute_raises(tmp_path: Path) -> None:
    middleware_file = tmp_path / "middleware.py"
    middleware_file.write_text("not_middleware = []\n")
    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([])
        .with_middleware(middleware_file)
    )
    with pytest.raises(RuntimeError, match="does not declare a top-level"):
        builder.create()


def test_with_middleware_path_wrong_type_raises(tmp_path: Path) -> None:
    middleware_file = tmp_path / "middleware.py"
    middleware_file.write_text("middleware = [object]\n")
    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([])
        .with_middleware(middleware_file)
    )
    with pytest.raises(TypeError, match="expected list"):
        builder.create()


def test_framework_middleware_implement_the_contract() -> None:
    from arvel.contracts import GlobalMiddleware

    assert issubclass(TrustProxiesMiddleware, GlobalMiddleware)
    assert issubclass(ArvelScopeMiddleware, GlobalMiddleware)
    assert not issubclass(object, GlobalMiddleware)
