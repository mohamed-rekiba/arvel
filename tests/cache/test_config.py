"""Tests for CacheSettings — NFR-038.

NFR-038: CacheSettings uses CACHE_ env prefix.
"""

from __future__ import annotations

import os
from unittest.mock import patch


class TestCacheSettings:
    """NFR-038: Typed config with CACHE_ env prefix."""

    def test_defaults(self, clean_env: None) -> None:
        from arvel.cache.config import CacheSettings

        settings = CacheSettings()
        assert settings.driver == "memory"
        assert settings.prefix == ""
        assert settings.default_ttl == 3600
        assert settings.redis_url == "redis://localhost:6379/0"

    def test_env_override(self) -> None:
        from arvel.cache.config import CacheSettings

        with patch.dict(
            os.environ,
            {
                "CACHE_DRIVER": "redis",
                "CACHE_PREFIX": "myapp:",
                "CACHE_DEFAULT_TTL": "600",
                "CACHE_REDIS_URL": "redis://prod:6379/1",
            },
        ):
            settings = CacheSettings()
            assert settings.driver == "redis"
            assert settings.prefix == "myapp:"
            assert settings.default_ttl == 600
            assert settings.redis_url == "redis://prod:6379/1"
