"""F1 — facade type stubs (spec 06 §42-50). The committed `.pyi` must stay in sync with the
live backing classes ("generated in CI ... never drift"): regenerate in-memory and compare."""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from arvel.kernel.globals import app, has_application, set_application

_GEN = Path(__file__).resolve().parent.parent / "tools" / "gen_facade_stubs.py"


@pytest.fixture(autouse=True)
def _restore_global_app() -> Iterator[None]:
    """The generator's ``_boot()`` calls ``Application…create()``, which ``set_application()``s the
    app globally. Snapshot + restore so this test never leaks a throwaway stub app into the global
    that later tests resolve through ``app()`` — keeping the suite order-independent."""
    prior = app() if has_application() else None
    yield
    set_application(prior)


def _load_generator() -> Any:
    spec = importlib.util.spec_from_file_location("gen_facade_stubs", _GEN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_facade_stub_is_up_to_date() -> None:
    gen = _load_generator()
    expected = gen._render(gen._boot())
    actual = gen.STUB_PATH.read_text()
    assert actual == expected, "facade stub is stale — run `make stubs` and commit the result"


def test_stub_exposes_explicit_method_arity() -> None:
    """A directly-introspectable method (Router.post) is stubbed with real arity, not just Any."""
    text = (_GEN.parent.parent / "src/arvel/support/facades/__init__.pyi").read_text()
    assert "class Route(Facade):" in text
    assert "def post(" in text  # router method visible to type-checkers
    # manager-proxied / unresolved facades fall back via the metaclass __getattr__
    assert "def __getattr__(cls, name: str) -> Any: ..." in text
