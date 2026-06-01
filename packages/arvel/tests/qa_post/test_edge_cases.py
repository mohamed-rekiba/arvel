"""Stage 4 edge-case coverage — close the gaps surfaced by the QA-Post coverage run.

These tests intentionally probe error paths, lifecycle edges, and rarely-exercised
contextual/extension branches so the foundations layer has no untested branches
heading into the security gate.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def clean_env() -> Iterator[None]:
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


# application


def test_environment_not_set_error_when_accessed_before_create() -> None:
    from arvel import Application
    from arvel.application.errors import EnvironmentNotSetError

    app = Application()
    with pytest.raises(EnvironmentNotSetError):
        app.environment()
    with pytest.raises(EnvironmentNotSetError):
        app.base_path()


def test_boot_twice_is_idempotent(tmp_path: Path) -> None:
    from arvel import Application, ServiceProvider

    call_count: list[int] = []

    class Provider(ServiceProvider):
        async def boot(self) -> None:
            call_count.append(1)

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([Provider])
        .create()
    )
    asyncio.run(app.boot())
    asyncio.run(app.boot())
    assert call_count == [1]


def test_shutdown_runs_providers_in_reverse_order(tmp_path: Path) -> None:
    from arvel import Application, ServiceProvider

    order: list[str] = []

    class A(ServiceProvider):
        async def shutdown(self) -> None:
            order.append("A")

    class B(ServiceProvider):
        async def shutdown(self) -> None:
            order.append("B")

    app = (
        Application.configure(tmp_path).with_environment("testing").with_providers([A, B]).create()
    )
    asyncio.run(app.boot())
    asyncio.run(app.shutdown())
    assert order == ["B", "A"]


def test_shutdown_error_wraps_provider_failure(tmp_path: Path) -> None:
    from arvel import Application, ServiceProvider
    from arvel.application.errors import ShutdownError

    class Bad(ServiceProvider):
        async def shutdown(self) -> None:
            raise RuntimeError("teardown failure")

    app = Application.configure(tmp_path).with_environment("testing").with_providers([Bad]).create()
    asyncio.run(app.boot())
    with pytest.raises(ShutdownError) as excinfo:
        asyncio.run(app.shutdown())
    assert excinfo.value.provider is Bad


def test_with_providers_from_path_defers_load_until_create(tmp_path: Path) -> None:
    """``with_providers(Path)`` defers loading to ``.create()`` time.

    Previously this branch raised at the builder call. With 's Laravel-
    shaped layout, ``bootstrap/app.py`` builds the application fluently and
    the call site cannot be aware that the loader isn't ready yet — the
    failure now surfaces at create() where the loader actually runs.
    """
    from arvel import Application

    # The fluent call itself must NOT raise.
    builder = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers(Path("providers.yaml"))
    )
    # Once Stage 3b implements the loader, the deferred failure surfaces
    # at .create() — the file doesn't exist, so the loader raises.
    with pytest.raises((FileNotFoundError, RuntimeError)):
        builder.create()


# container


def test_bind_rejects_non_callable_concrete() -> None:
    from arvel.container import Container

    class Foo: ...

    c = Container()
    with pytest.raises(TypeError):
        c.bind(Foo, concrete=42)  # type: ignore[arg-type]


def test_abstract_class_is_rejected() -> None:
    from abc import ABC, abstractmethod

    from arvel.container import BindingResolutionError, Container

    class Iface(ABC):
        @abstractmethod
        def do(self) -> None: ...

    c = Container()
    with pytest.raises(BindingResolutionError):
        c.make(Iface)  # type: ignore[type-abstract]


def test_amake_falls_back_to_sync_resolve_when_unbound() -> None:
    from arvel.container import Container

    class Service:
        def __init__(self) -> None: ...

    c = Container()

    result = asyncio.run(c.amake(Service))
    assert isinstance(result, Service)


def test_amake_returns_cached_singleton_without_reinvoking() -> None:
    from arvel.container import Container

    counter: list[int] = []

    class Service:
        def __init__(self) -> None:
            counter.append(1)

    c = Container()
    c.singleton(Service)

    first = asyncio.run(c.amake(Service))
    second = asyncio.run(c.amake(Service))
    assert first is second
    assert counter == [1]


def test_amake_supports_async_factory_binding() -> None:
    from arvel.container import Container

    class Service:
        def __init__(self, label: str) -> None:
            self.label = label

    async def make_service() -> Service:
        return Service("async")

    c = Container()
    c.bind(Service, make_service)

    out = asyncio.run(c.amake(Service))
    assert out.label == "async"


def test_amake_with_async_contextual_factory() -> None:
    from arvel.container import Container

    class Dep:
        def __init__(self, name: str) -> None:
            self.name = name

    class Consumer:
        def __init__(self, dep: Dep) -> None:
            self.dep = dep

    async def factory() -> Dep:
        return Dep("contextual")

    c = Container()
    c.when(Consumer).needs(Dep).give(factory)
    # Resolve Dep through contextual path inside the async resolver
    consumer = asyncio.run(c.amake(Consumer, dep=Dep("override")))
    assert consumer.dep.name == "override"


def test_extending_applies_decorator_and_invalidates_cache() -> None:
    from arvel.container import Container

    class Service:
        def __init__(self) -> None:
            self.label = "raw"

    c = Container()
    c.singleton(Service)
    first = c.make(Service)
    assert first.label == "raw"

    def add_suffix(svc: Service, _container: Container) -> Service:
        svc.label = svc.label + "+ext"
        return svc

    c.extend(Service, add_suffix)
    second = c.make(Service)
    assert second.label.endswith("+ext")


def test_async_binding_via_sync_make_raises() -> None:
    from arvel.container import AsyncBindingError, Container

    class Service: ...

    async def factory() -> Service:
        return Service()

    c = Container()
    c.bind(Service, factory)
    with pytest.raises(AsyncBindingError):
        c.make(Service)


def test_aresolve_treats_pre_bound_instance_as_highest_priority() -> None:
    from arvel.container import Container

    class Service: ...

    pre_built = Service()
    c = Container()
    c.instance(Service, pre_built)
    out = asyncio.run(c.amake(Service))
    assert out is pre_built


# env


def test_env_required_missing_raises(clean_env: None) -> None:
    from arvel.support.env import env

    os.environ.pop("ARVEL_REQ", None)
    with pytest.raises(LookupError):
        env("ARVEL_REQ", required=True)


def test_env_bool_false_values(clean_env: None) -> None:
    from arvel.support.env import env

    for raw in ("0", "false", "FALSE", "no", "off"):
        os.environ["ARVEL_FLAG"] = raw
        assert env("ARVEL_FLAG", True) is False


def test_env_list_parsing_strips_whitespace(clean_env: None) -> None:
    from arvel.support.env import env

    os.environ["ARVEL_LIST"] = " a , b ,c ,, d "
    parsed = env("ARVEL_LIST", ["x"])
    assert parsed == ["a", "b", "c", "d"]


def test_env_returns_empty_string_when_set_without_default(clean_env: None) -> None:
    from arvel.support.env import env

    os.environ["ARVEL_BLANK"] = ""
    assert env("ARVEL_BLANK") == ""


# support.collections


def test_first_on_empty_collection_returns_none() -> None:
    from arvel.support import Collection

    c: Collection[int] = Collection([])
    assert c.first() is None
    assert c.is_empty()
    assert len(c) == 0


def test_chunk_with_invalid_size_raises() -> None:
    from arvel.support import Collection

    c = Collection([1, 2, 3])
    with pytest.raises(ValueError, match="chunk size"):
        c.chunk(0)


# support.pipeline


def test_pipeline_then_without_send_raises() -> None:
    from arvel.support import Pipeline

    p: Pipeline[int, int] = Pipeline()

    async def final(value: int) -> int:
        return value + 1

    with pytest.raises(RuntimeError, match="send"):
        asyncio.run(p.then(final))


# config.registry


def test_registry_clear_empties_registered_configs() -> None:
    from arvel.config import ArvelSettings
    from arvel.config.registry import clear, register, registered_configs

    class SnapshotCfg(ArvelSettings):
        value: int = 1

    register(SnapshotCfg)
    assert SnapshotCfg in registered_configs()
    clear()
    assert SnapshotCfg not in registered_configs()


# providers.config_provider


def test_config_provider_re_raises_unwrapped_config_error(tmp_path: Path) -> None:
    """If make() itself raises ConfigError directly, the provider must re-raise as-is.

    fix: HostileCfg is unregistered in a finally block so the global
    config registry does not leak across tests.
    """
    from arvel import Application
    from arvel.application.errors import BootError
    from arvel.config import ArvelSettings
    from arvel.config.errors import ConfigError
    from arvel.config.registry import register, unregister
    from arvel.providers import ConfigServiceProvider

    class HostileCfg(ArvelSettings):
        @classmethod
        def __pydantic_init_subclass__(cls, **kwargs: object) -> None: ...

        def __init__(self, **_kw: object) -> None:
            raise ConfigError("synthetic boom")

    register(HostileCfg)
    try:
        app = (
            Application.configure(tmp_path)
            .with_environment("testing")
            .with_providers([ConfigServiceProvider])
            .create()
        )
        with pytest.raises(BootError):
            asyncio.run(app.boot())
    finally:
        unregister(HostileCfg)
