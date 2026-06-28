"""Providers + discovery — base, integration verbs, entry-point merge, deferred."""

from __future__ import annotations

from typing import Any

from arvel.kernel import (
    Application,
    ServiceProvider,
    clear_cache,
    discover_providers,
    lifespan,
    set_application,
)
from arvel.kernel.provider import KernelServiceProvider


class Widget:
    pass


class RecordingProvider(ServiceProvider):
    def register(self) -> None:
        self.app.singleton(Widget)
        self.load_routes_from("routes/web.py")
        self.load_migrations_from("db/migrations")
        self.load_views_from("resources/views", "app")
        self.load_translations_from("lang", "app")
        self.commands("cmd-a", "cmd-b")
        self.publishes({"src/cfg.py": "config/cfg.py"}, tag="config")
        self.merge_config_from({"size": "L", "color": "red"}, "widget")


class DeferredProvider(ServiceProvider):
    def register(self) -> None:
        self.app.singleton("deferred-svc", lambda: "D")

    def provides(self) -> list[Any]:
        return ["deferred-svc"]


def test_verbs_record_into_registries() -> None:
    app = Application()
    RecordingProvider(app).register()
    assert app.route_files == ["routes/web.py"]
    assert app.migration_paths == ["db/migrations"]
    assert app.view_namespaces == {"app": "resources/views"}
    assert app.translation_namespaces == {"app": "lang"}
    assert app.command_classes == ["cmd-a", "cmd-b"]
    assert app.published["config"] == {"src/cfg.py": "config/cfg.py"}
    assert isinstance(app.make(Widget), Widget)


def test_merge_config_from_existing_wins() -> None:
    app = Application()
    app.make("config").set("widget", {"size": "S"})  # app value present
    RecordingProvider(app).register()
    cfg = app.make("config")
    assert cfg.get("widget.size") == "S"  # existing wins
    assert cfg.get("widget.color") == "red"  # default merged in


def test_merge_config_from_scalar_existing_wins() -> None:
    # M2: an app's explicit scalar override must survive a provider merge (existing wins).
    app = Application()
    app.make("config").set("widget", "custom")  # deliberate scalar override
    RecordingProvider(app).register()  # merges {"size": "L", "color": "red"} under "widget"
    assert app.make("config").get("widget") == "custom"  # not clobbered by defaults


def test_merge_config_from_does_not_mutate_source_defaults() -> None:
    # H2: a provider's defaults are often a module-level constant — merging must not alias or mutate
    # the nested source objects into the live repo.
    defaults = {"widget": {"size": "L", "opts": {"a": 1}}}
    source_widget = defaults["widget"]
    app = Application()
    app.make("config").set("widget", {"size": "S"})  # existing wins on the merge
    Provider = type(
        "P",
        (ServiceProvider,),
        {"register": lambda self: self.merge_config_from(defaults["widget"], "widget")},
    )
    Provider(app).register()
    # later runtime mutation of the repo must not reach back into the source constant
    app.make("config").set("widget.opts.a", 999)
    assert source_widget == {"size": "L", "opts": {"a": 1}}  # pristine


def test_discover_finds_kernel_entry_point() -> None:
    clear_cache()
    providers = discover_providers(Application(), use_cache=False)
    assert KernelServiceProvider in providers


def test_dont_discover_excludes() -> None:
    clear_cache()
    app = Application()
    app.make("config").set("app", {"dont_discover": ["kernel"]})
    providers = discover_providers(app, use_cache=False)
    assert KernelServiceProvider not in providers
    clear_cache()


async def test_lifespan_registers_discovered_providers() -> None:
    clear_cache()
    app = Application()
    async with lifespan(app):
        assert KernelServiceProvider in app.registered_provider_types
    set_application(None)


def test_deferred_provider_registers_on_first_resolve() -> None:
    app = Application()
    app.register_deferred(DeferredProvider(app))
    assert app.bound("deferred-svc") is False  # register() not run yet
    assert app.make("deferred-svc") == "D"  # resolving triggers registration
    assert app.bound("deferred-svc") is True
