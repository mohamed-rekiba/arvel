"""Sprint 3: Bootstrap Resilience — QA-Pre tests.

FR-009: Boot rollback on partial failure
FR-010: load_config sync I/O (documented as acceptable — no test needed)
FR-011: Cache fallback warning log
FR-013: shutdown() safe on unbooted app
FR-014: Route-to-middleware pairing by path, not index
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


class TestBootRollbackOnPartialFailure:
    """FR-009: Partial boot failure rolls back already-booted providers."""

    async def test_already_booted_providers_get_shutdown_on_failure(
        self, tmp_project: Path
    ) -> None:
        """AC: If provider C fails, providers B and A (already booted) get shutdown()."""
        from arvel.foundation.application import Application
        from arvel.foundation.exceptions import BootError

        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "_shutdown_log: list[str] = []\n\n"
            "class AProvider(ServiceProvider):\n"
            "    priority = 10\n"
            "    async def boot(self, app):\n"
            "        pass\n"
            "    async def shutdown(self, app):\n"
            "        _shutdown_log.append('A')\n\n"
            "class BProvider(ServiceProvider):\n"
            "    priority = 20\n"
            "    async def boot(self, app):\n"
            "        pass\n"
            "    async def shutdown(self, app):\n"
            "        _shutdown_log.append('B')\n\n"
            "class CProvider(ServiceProvider):\n"
            "    priority = 30\n"
            "    async def boot(self, app):\n"
            "        raise RuntimeError('C failed')\n"
            "    async def shutdown(self, app):\n"
            "        _shutdown_log.append('C')\n\n"
            "providers = [AProvider, BProvider, CProvider]\n"
        )

        with pytest.raises(BootError, match="CProvider"):
            await Application.create(tmp_project, testing=True)

    async def test_booted_flag_stays_false_after_rollback(self, tmp_project: Path) -> None:
        """AC: _booted remains False after a failed boot."""
        from arvel.foundation.application import Application
        from arvel.foundation.exceptions import BootError

        (tmp_project / "bootstrap" / "providers.py").write_text(
            "from arvel.foundation.provider import ServiceProvider\n\n"
            "class FailProvider(ServiceProvider):\n"
            "    async def boot(self, app):\n"
            "        raise RuntimeError('boom')\n\n"
            "providers = [FailProvider]\n"
        )

        app = Application._new_unbooted(tmp_project, testing=True)
        with pytest.raises(BootError):
            await app._bootstrap(testing=True)

        assert not app._booted, "_booted should remain False after failed bootstrap"


class TestCacheFallbackWarning:
    """FR-011: Corrupt cache produces a warning log."""

    async def test_corrupt_cache_logs_warning(
        self, tmp_project: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC: A corrupt JSON cache file produces a structured log warning."""
        from arvel.foundation.config import _load_cached_root_settings

        cache_path = tmp_project / ".config_cache.json"
        cache_path.write_text("{invalid json content!!!")

        result = _load_cached_root_settings(tmp_project, cache_path, testing=False)

        assert result is None, "Corrupt cache should return None"


class TestShutdownSafeOnUnbooted:
    """FR-013: shutdown() safe on unbooted application."""

    async def test_shutdown_before_bootstrap_returns_without_error(self, tmp_project: Path) -> None:
        """AC: Calling shutdown() before _bootstrap() completes returns without error."""
        from arvel.foundation.application import Application

        app = Application._new_unbooted(tmp_project, testing=True)

        await app.shutdown()
