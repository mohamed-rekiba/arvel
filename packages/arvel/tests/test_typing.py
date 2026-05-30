"""FR-001-002: Type-checker baseline.

Assertions checked at type-check time via typing.assert_type. The test bodies also
run at runtime as a sanity check, but the real test happens under
``mypy --strict`` and ``pyright --strict``.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_type


def test_container_make_returns_typed_T() -> None:
    from arvel.container import Container

    class Foo:
        def __init__(self) -> None: ...

    c = Container()
    c.bind(Foo)
    obj = c.make(Foo)
    assert_type(obj, Foo)


async def test_container_amake_returns_typed_T() -> None:
    from arvel.container import Container

    class Foo:
        def __init__(self) -> None: ...

    c = Container()
    c.bind(Foo)
    obj = await c.amake(Foo)
    assert_type(obj, Foo)


def test_config_of_returns_typed_settings() -> None:
    from arvel.config import ArvelSettings, Config
    from arvel.container import Container

    class MyCfg(ArvelSettings):
        name: str = "x"

    c = Container()
    c.singleton(MyCfg)
    Config.bind(c)
    out = Config.of(MyCfg)
    assert_type(out, MyCfg)


def test_application_builder_chain_returns_builder() -> None:
    from arvel import Application, ApplicationBuilder

    b1 = Application.configure(Path())
    assert_type(b1, ApplicationBuilder)
    b2 = b1.with_environment("x")
    assert_type(b2, ApplicationBuilder)


def test_application_create_returns_application() -> None:
    from arvel import Application

    app = Application.configure(Path()).with_environment("x").create()
    assert_type(app, Application)


def test_dep_returns_callable_returning_T() -> None:
    from arvel import dep

    class Service:
        def __init__(self) -> None: ...

    resolver = dep(Service)
    assert callable(resolver)
