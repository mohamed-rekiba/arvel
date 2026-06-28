"""T2.1 — facades: static-looking proxies to container-resolved services."""

from __future__ import annotations

from arvel.kernel import Application, set_application
from arvel.kernel.provider import KernelServiceProvider
from arvel.support.facades import Config, Facade, Log


def _boot_app() -> Application:
    app = Application()
    app.make("config").set("app", {"name": "myapp"})
    KernelServiceProvider(app).register()  # binds log
    set_application(app)
    return app


def test_config_facade_forwards_to_root() -> None:
    _boot_app()
    try:
        assert Config.get("app.name") == "myapp"
        assert Config.has("app.name") is True
        assert Config.get("app.missing", "d") == "d"
    finally:
        Facade.clear_swapped()
        set_application(None)


def test_log_facade_forwards() -> None:
    _boot_app()
    try:
        Log.info("hello", k=1)  # forwards to LogManager.info; must not raise
    finally:
        Facade.clear_swapped()
        set_application(None)


def test_swap_overrides_root() -> None:
    _boot_app()

    class FakeConfig:
        def get(self, key: str, default: object = None) -> str:
            return "swapped"

    try:
        Config.swap(FakeConfig())
        assert Config.get("anything") == "swapped"
    finally:
        Facade.clear_swapped()
        set_application(None)


def test_accessors() -> None:
    assert Config.accessor() == "config"
    assert Log.accessor() == "log"


def test_lazy_top_level_exports() -> None:
    import arvel

    assert arvel.Config is Config
    assert arvel.Log is Log


def test_validator_facade_is_exported_from_arvel() -> None:
    # validation.md / facades.md document `from arvel import Validator` (the facade, `.make()`),
    # distinct from the `from arvel.validation import Validator` class. It must be exported top-level.
    import arvel
    from arvel.support.facades import Validator as ValidatorFacade

    assert arvel.Validator is ValidatorFacade
    assert ValidatorFacade.accessor() == "validator"
