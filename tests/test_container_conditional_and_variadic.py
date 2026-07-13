"""Conditional binds (bind_if/singleton_if/scoped_if), contextual give_tagged/give_config,
and variadic (*args) constructor injection."""

from __future__ import annotations

import pytest

from arvel.kernel.config import Repository
from arvel.kernel.container import Container


class Port:
    pass


class AdapterA(Port):
    pass


class AdapterB(Port):
    pass


# --- conditional binds -------------------------------------------------------


def test_bind_if_respects_existing_binding() -> None:
    c = Container()
    c.bind(Port, AdapterA)
    c.bind_if(Port, AdapterB)
    assert isinstance(c.make(Port), AdapterA)


def test_bind_if_registers_when_unbound() -> None:
    c = Container()
    c.bind_if(Port, AdapterB)
    assert isinstance(c.make(Port), AdapterB)


def test_singleton_if_respects_existing_and_shares_when_new() -> None:
    c = Container()
    c.singleton(Port, AdapterA)
    first = c.make(Port)
    c.singleton_if(Port, AdapterB)
    assert c.make(Port) is first  # untouched: still the original shared AdapterA

    c2 = Container()
    c2.singleton_if(Port, AdapterB)
    assert c2.make(Port) is c2.make(Port)


def test_scoped_if_registers_scoped_only_when_unbound() -> None:
    c = Container()
    c.scoped_if(Port, AdapterA)
    with c.scope():
        assert c.make(Port) is c.make(Port)
    c.scoped_if(Port, AdapterB)  # already bound — no-op
    with c.scope():
        assert isinstance(c.make(Port), AdapterA)


def test_bind_if_sees_instance_registrations() -> None:
    c = Container()
    c.instance(Port, AdapterA())
    c.bind_if(Port, AdapterB)
    assert isinstance(c.make(Port), AdapterA)


# --- contextual give_tagged / give_config ------------------------------------


class TaggedConsumer:
    def __init__(self, ports: list[Port]) -> None:
        self.ports = ports


def test_give_tagged_injects_tagged_instances_in_registration_order() -> None:
    c = Container()
    c.bind(AdapterA)
    c.bind(AdapterB)
    c.tag([AdapterA, AdapterB], "ports")
    c.when(TaggedConsumer).needs("ports").give_tagged("ports")
    consumer = c.make(TaggedConsumer)
    assert [type(p) for p in consumer.ports] == [AdapterA, AdapterB]


def test_give_tagged_empty_tag_injects_empty_list() -> None:
    c = Container()
    c.when(TaggedConsumer).needs("ports").give_tagged("nothing-here")
    assert c.make(TaggedConsumer).ports == []


class NeedsKey:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


def test_give_config_injects_config_value() -> None:
    c = Container()
    config = Repository()
    config.set("services.search.key", "abc123")
    c.instance("config", config)
    c.when(NeedsKey).needs("api_key").give_config("services.search.key")
    assert c.make(NeedsKey).api_key == "abc123"


def test_give_config_missing_key_uses_default() -> None:
    c = Container()
    c.instance("config", Repository())
    c.when(NeedsKey).needs("api_key").give_config("services.search.key", "fallback")
    assert c.make(NeedsKey).api_key == "fallback"


# --- variadic injection -------------------------------------------------------


class VariadicPipeline:
    def __init__(self, *filters: Port) -> None:
        self.filters = filters


def test_variadic_param_resolves_all_bindings_of_the_type() -> None:
    c = Container()
    c.bind(AdapterA)
    c.bind(AdapterB)
    pipeline = c.make(VariadicPipeline)
    assert [type(f) for f in pipeline.filters] == [AdapterA, AdapterB]


def test_variadic_param_with_no_bindings_resolves_empty() -> None:
    c = Container()
    pipeline = c.make(VariadicPipeline)
    assert pipeline.filters == ()


def test_variadic_param_contextual_list_wins_over_type_scan() -> None:
    c = Container()
    c.bind(AdapterA)
    c.when(VariadicPipeline).needs("filters").give([AdapterB])
    pipeline = c.make(VariadicPipeline)
    assert [type(f) for f in pipeline.filters] == [AdapterB]


def test_variadic_keyword_only_params_after_star_still_inject() -> None:
    class Mixed:
        def __init__(self, *filters: Port, config: Repository) -> None:
            self.filters = filters
            self.config = config

    c = Container()
    c.bind(AdapterA)
    repo = Repository()
    c.instance(Repository, repo)
    obj = c.make(Mixed)
    assert [type(f) for f in obj.filters] == [AdapterA]
    assert obj.config is repo


@pytest.mark.parametrize("verb", ["bind_if", "singleton_if", "scoped_if"])
def test_conditional_verbs_respect_aliases(verb: str) -> None:
    c = Container()
    c.alias("port", Port)
    c.bind("port", AdapterA)
    getattr(c, verb)(Port, AdapterB)  # alias and abstract are the same key — stay bound
    assert isinstance(c.make(Port), AdapterA)


def test_variadic_param_give_tagged_resolves_the_tag_list() -> None:
    c = Container()
    c.bind(AdapterA)
    c.bind(AdapterB)
    c.tag([AdapterA, AdapterB], "ports")
    c.when(VariadicPipeline).needs("filters").give_tagged("ports")
    pipeline = c.make(VariadicPipeline)
    assert [type(f) for f in pipeline.filters] == [AdapterA, AdapterB]


def test_variadic_type_scan_preserves_interleaved_registration_order() -> None:
    c = Container()
    c.instance(AdapterA, AdapterA())
    c.bind(AdapterB)
    pipeline = c.make(VariadicPipeline)
    assert [type(f) for f in pipeline.filters] == [AdapterA, AdapterB]
