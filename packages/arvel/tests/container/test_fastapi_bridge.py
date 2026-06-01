"""FastAPI bridge via arvel.dep()."""

from __future__ import annotations


class Service:
    def __init__(self) -> None:
        self.id = id(self)


def test_dep_returns_callable() -> None:
    from arvel import dep

    resolver = dep(Service)
    assert callable(resolver)


def test_dep_resolves_from_request_state_scope() -> None:
    """The dep callable expects a request-like object with a `.state.arvel_scope` attr."""
    from types import SimpleNamespace

    from arvel import dep
    from arvel.container import Container

    c = Container()
    with c.scope() as scoped:
        scoped.bind(Service)
        request = SimpleNamespace(state=SimpleNamespace(arvel_scope=scoped))
        resolver = dep(Service)
        obj = resolver(request)
        assert isinstance(obj, Service)


def test_dep_without_scope_raises_clear_error() -> None:
    from types import SimpleNamespace

    import pytest
    from arvel import dep

    request = SimpleNamespace(state=SimpleNamespace())
    resolver = dep(Service)
    with pytest.raises(RuntimeError, match="scope"):
        resolver(request)
