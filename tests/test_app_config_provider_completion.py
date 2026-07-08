"""Environment matcher, typed config getters, config set-form, provider declarative
bindings, and the capability registries living in the container instead of on the kernel."""

from __future__ import annotations

import pytest

from arvel.kernel.application import Application
from arvel.kernel.config import ConfigTypeError, Repository, config
from arvel.kernel.container import Container
from arvel.kernel.globals import set_application
from arvel.kernel.service_provider import ServiceProvider


def _app(env: str = "local") -> Application:
    app = Application()
    app.make("config").set("app.env", env)
    return app


# --- environment matcher -------------------------------------------------------


def test_environment_no_args_returns_current_env() -> None:
    assert _app("staging").environment() == "staging"


def test_environment_matches_membership_and_wildcards() -> None:
    app = _app("local")
    assert app.environment("local") is True
    assert app.environment("staging", "production") is False
    assert app.environment("loc*") is True
    assert _app("integration-testing").environment("*-testing") is True


def test_is_local_and_is_production_shortcuts() -> None:
    assert _app("local").is_local() is True
    assert _app("production").is_production() is True
    assert _app("local").is_production() is False


# --- typed config getters --------------------------------------------------------


def test_typed_getters_return_matching_values() -> None:
    repo = Repository({"a": {"s": "x", "i": 3, "f": 1.5, "b": True, "l": [1, 2]}})
    assert repo.string("a.s") == "x"
    assert repo.integer("a.i") == 3
    assert repo.float("a.f") == 1.5
    assert repo.boolean("a.b") is True
    assert repo.array("a.l") == [1, 2]


def test_typed_getters_raise_on_mismatch() -> None:
    repo = Repository({"a": {"s": 5, "b": "yes", "l": "not-a-list"}})
    with pytest.raises(ConfigTypeError):
        repo.string("a.s")
    with pytest.raises(ConfigTypeError):
        repo.boolean("a.b")
    with pytest.raises(ConfigTypeError):
        repo.array("a.l")


def test_typed_getter_edges() -> None:
    repo = Repository({"a": {"b": True, "i": 7}})
    with pytest.raises(ConfigTypeError):
        repo.integer("a.b")  # bool is not an integer
    assert repo.float("a.i") == 7.0  # int widens to float
    with pytest.raises(ConfigTypeError):
        repo.string("missing.key")  # missing + no default → typed error, not None
    assert repo.string("missing.key", "dflt") == "dflt"


# --- config() mapping-set form ----------------------------------------------------


def test_config_helper_mapping_sets_values() -> None:
    app = _app()
    set_application(app)
    try:
        config({"feature.flag": True, "app.name": "renamed"})
        assert config("feature.flag") is True
        assert config("app.name") == "renamed"
    finally:
        set_application(None)


# --- provider declarative bindings -------------------------------------------------


class Contract:
    pass


class Impl(Contract):
    pass


def test_provider_declarative_bindings_and_singletons_auto_register() -> None:
    class DeclarativeProvider(ServiceProvider):
        bindings = {Contract: Impl}
        singletons = {"decl.single": Impl}

    app = _app()
    app.register(DeclarativeProvider(app))
    assert isinstance(app.make(Contract), Impl)
    assert app.make(Contract) is not app.make(Contract)  # bind, not shared
    assert app.make("decl.single") is app.make("decl.single")  # singleton


# --- capability registries off the kernel object -----------------------------------


def test_application_no_longer_carries_capability_registries() -> None:
    app = _app()
    for attr in (
        "view_namespaces",
        "migration_paths",
        "translation_namespaces",
        "command_classes",
        "console_commands",
        "published",
    ):
        assert not hasattr(app, attr), attr


def test_provider_verbs_populate_container_registries() -> None:
    class PkgProvider(ServiceProvider):
        def register(self) -> None:
            self.load_views_from("pkg/views", "pkg")
            self.load_migrations_from("pkg/migrations")
            self.load_translations_from("pkg/lang", "pkg")
            self.publishes({"pkg/conf.py": "config/pkg.py"}, tag="pkg-config")

    app = _app()
    app.register(PkgProvider(app))
    assert app.registry("views.namespaces", dict) == {"pkg": "pkg/views"}
    assert app.registry("database.migration_paths", list) == ["pkg/migrations"]
    assert app.registry("localization.namespaces", dict) == {"pkg": "pkg/lang"}
    assert app.registry("console.published", dict) == {
        "pkg-config": {"pkg/conf.py": "config/pkg.py"}
    }


def test_registries_survive_flush() -> None:
    app = _app()
    app.registry("console.commands", list).append(object)
    app.flush()
    assert len(app.registry("console.commands", list)) == 1


async def test_view_namespace_reaches_the_view_factory(tmp_path) -> None:
    (tmp_path / "greeting.html").write_text("hello {{ name }}")

    class BlogProvider(ServiceProvider):
        def register(self) -> None:
            self.load_views_from(str(tmp_path), "blog")

    app = _app()
    set_application(app)
    try:
        from arvel.views import View
        from arvel.views.provider import ViewServiceProvider

        app.make("config").set("view", {"paths": [str(tmp_path)]})
        app.register(ViewServiceProvider(app))
        app.register(BlogProvider(app))
        rendered = await app.make("view").render(View("blog::greeting.html", {"name": "world"}))
        assert rendered == "hello world"
    finally:
        set_application(None)


async def test_view_namespace_applies_when_factory_already_resolved(tmp_path) -> None:
    (tmp_path / "late.html").write_text("late {{ n }}")

    app = _app()
    set_application(app)
    try:
        from arvel.views import View
        from arvel.views.provider import ViewServiceProvider

        app.make("config").set("view", {"paths": [str(tmp_path)]})
        app.register(ViewServiceProvider(app))
        app.make("view")  # materialize first

        class LateProvider(ServiceProvider):
            def register(self) -> None:
                self.load_views_from(str(tmp_path), "late")

        app.register(LateProvider(app))
        assert await app.make("view").render(View("late::late.html", {"n": 1})) == "late 1"
    finally:
        set_application(None)


def test_container_resolved_reports_materialized_only() -> None:
    c = Container()
    c.singleton(Impl)
    assert c.resolved(Impl) is False
    c.make(Impl)
    assert c.resolved(Impl) is True
