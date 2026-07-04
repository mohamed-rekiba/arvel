"""A Manager(app) reads THAT app's config section, not just the global one."""

from __future__ import annotations

from arvel.cache import CacheManager
from arvel.kernel import Application, set_application


def test_manager_uses_its_own_app_config_not_the_global() -> None:
    global_app = Application()
    global_app.make("config").set("cache", {"default": "array"})
    set_application(global_app)
    try:
        # a DIFFERENT app whose cache config differs from the global
        other_app = Application()
        other_app.make("config").set("cache", {"default": "redis", "url": "redis://example/0"})

        manager = CacheManager(other_app)
        # reads other_app's config ("redis"), NOT the global app's ("array")
        assert manager.default_driver() == "redis"

        # and a manager bound to the global app still reflects the global config
        assert CacheManager(global_app).default_driver() == "array"
        # no app → falls back to the global config
        assert CacheManager().default_driver() == "array"
    finally:
        set_application(None)
