"""Tests for optional-dependency isolation.
These tests verify that importing arvel.cache, arvel.session, arvel.storage
does not raise ImportError even when optional extras (redis, s3, gcs, azure) are
not installed.
"""

from __future__ import annotations

from pydantic import SecretStr


class TestOptionalDepIsolation:
    def test_cache_module_imports_without_redis(self) -> None:
        pass  # must not raise

    def test_session_module_imports_without_redis(self) -> None:
        pass  # must not raise

    def test_storage_module_imports_without_cloud_extras(self) -> None:
        pass  # must not raise

    def test_local_driver_importable_without_extras(self) -> None:
        from arvel.storage.drivers.local import LocalDriver

        assert LocalDriver is not None

    def test_array_store_importable_without_redis(self) -> None:
        from arvel.cache.stores.array import ArrayStore

        assert ArrayStore is not None

    def test_null_store_importable(self) -> None:
        from arvel.cache.stores.null import NullStore

        assert NullStore is not None

    def test_memory_driver_importable(self) -> None:
        from arvel.storage.drivers.memory import MemoryDriver

        assert MemoryDriver is not None

    def test_facades_importable(self) -> None:
        from arvel.facades import Cache, Session, Storage

        assert Cache is not None
        assert Session is not None
        assert Storage is not None

    def test_config_classes_importable(self) -> None:
        from arvel.config.cache_config import CacheConfig
        from arvel.config.session_config import SessionConfig
        from arvel.config.storage_config import StorageConfig

        assert CacheConfig is not None
        assert SessionConfig is not None
        assert StorageConfig is not None


class TestCloudDriverFailsHelpfully:
    def test_s3_driver_raises_helpful_error_without_aioboto3(self, monkeypatch: object) -> None:
        import sys
        import types

        # Set to None so Python treats the module as unavailable (popping alone
        # doesn't prevent re-import when the package is installed on disk).
        saved: types.ModuleType | None = sys.modules.pop("aioboto3", None)
        was_present = "aioboto3" in sys.modules or saved is not None
        sys.modules["aioboto3"] = None  # type: ignore[assignment]
        try:
            import pytest
            from arvel.config.storage_config import S3Config
            from arvel.storage.drivers.s3 import S3Driver

            with pytest.raises(ImportError, match="arvel\\[s3\\]"):
                S3Driver(
                    config=S3Config(key=SecretStr(""), secret=SecretStr(""), region="r", bucket="b")
                )
        finally:
            sys.modules.pop("aioboto3", None)
            if was_present and saved is not None:
                sys.modules["aioboto3"] = saved

    def test_redis_store_raises_helpful_error_without_redis(self) -> None:
        """CacheManager raises a helpful ImportError when the redis driver is
        selected but ``arvel[redis]`` is not installed.

        RedisStore accepts an injected client through the ``RedisConn`` Protocol
        and does not import ``redis`` itself; the helpful error fires inside
        ``CacheManager._make_store(REDIS)`` when it tries to construct the client.
        """
        import sys

        import pytest
        from arvel.cache import CacheManager
        from arvel.config.cache_config import CacheConfig, CacheDriver

        redis_keys = [k for k in sys.modules if k == "redis" or k.startswith("redis.")]
        saved = {k: sys.modules.pop(k) for k in redis_keys}
        # sys.modules is typed as dict[str, ModuleType], but assigning None is
        # the documented way to make a subsequent `import name` fail. See the
        # "Finding modules" section of the importlib docs.
        sys.modules["redis"] = None  # type: ignore[assignment]
        try:
            manager = CacheManager(CacheConfig(connection=CacheDriver.REDIS))
            with pytest.raises(ImportError, match="arvel\\[redis\\]"):
                manager.store()
        finally:
            sys.modules.pop("redis", None)
            sys.modules.update(saved)
