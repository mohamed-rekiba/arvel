"""Tests for GcsDriver

The ``TestGcsDriverOps`` suite exercises real put/get/exists/delete against
an ``fsouza/fake-gcs-server`` container booted by the session-scoped
:func:`gcs_endpoint` fixture (see
``packages/arvel/tests/integration/emulators/fixtures.py``).
The ``TestGcsDriverImportError`` suite stays as a pure unit test — it only
verifies the helpful error message when ``arvel[gcs]`` isn't installed.
"""

from __future__ import annotations

import sys
from typing import Protocol

import pytest
import pytest_asyncio

google_cloud_storage = pytest.importorskip(
    "google.cloud.storage", reason="arvel[gcs] not installed"
)

from arvel.config.storage_config import GcsConfig  # noqa: E402
from arvel.storage.drivers.gcs import GcsDriver  # noqa: E402


class GcsEndpoint(Protocol):
    """Structural type for the ``gcs_endpoint`` fixture (see emulators/fixtures.py).

    Declared inline instead of imported so the test stays self-contained and
    mypy doesn't have to resolve cross-directory test imports.
    """

    api_endpoint: str
    project: str
    bucket: str


class TestGcsDriverImportError:
    def test_helpful_import_error_without_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """helpful ImportError when arvel[gcs] not installed.

        Pinning ``sys.modules["google.cloud.storage"] = None`` is the
        documented way to make Python's import machinery treat a package as
        unavailable, even when it's installed on disk.
        """
        monkeypatch.setitem(sys.modules, "google.cloud.storage", None)

        with pytest.raises(ImportError, match=r"arvel\[gcs\]"):
            GcsDriver(config=GcsConfig(project="p", bucket="b"))


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestGcsDriverOps:
    @pytest_asyncio.fixture
    async def driver(self, gcs_endpoint: GcsEndpoint) -> GcsDriver:
        # fake-gcs-server accepts anonymous requests; the GCS client otherwise
        # tries to load Google ADC and fails. Pointing client_options at the
        # local emulator endpoint is the standard local-dev pattern.
        # Lazy + Any-typed import follows the same convention as
        # ``arvel.storage.drivers.gcs_`` (google-auth lacks py.typed marker).
        import importlib
        from typing import Any

        auth_creds: Any = importlib.import_module("google.auth.credentials")
        return GcsDriver(
            config=GcsConfig(project=gcs_endpoint.project, bucket=gcs_endpoint.bucket),
            # ``project`` and ``credentials`` are forwarded through to the
            # underlying ``google.cloud.storage.Client`` via ``**client_kwargs``;
            # the driver itself only reads ``bucket`` from the typed config.
            project=gcs_endpoint.project,
            credentials=auth_creds.AnonymousCredentials(),
            client_options={"api_endpoint": gcs_endpoint.api_endpoint},
        )

    async def test_put_and_get(self, driver: GcsDriver) -> None:
        # Single round-trip the four core operations against
        # fake-gcs-server: absence → put → exists → get → delete → absence.
        assert await driver.exists("ops/put_and_get.txt") is False
        assert await driver.put("ops/put_and_get.txt", b"hello gcs") is True
        assert await driver.exists("ops/put_and_get.txt") is True
        assert await driver.get("ops/put_and_get.txt") == b"hello gcs"
        assert await driver.delete("ops/put_and_get.txt") is True
        assert await driver.exists("ops/put_and_get.txt") is False

    async def test_temporary_url(self, driver: GcsDriver) -> None:
        # ``generate_signed_url`` requires service-account credentials with a
        # private key; under anonymous credentials the client raises
        # AttributeError before any wire activity. Verifying the contract
        # without round-tripping to fake-gcs is sufficient.
        with pytest.raises((AttributeError, Exception), match=r"(?i)credentials|sign"):
            driver.temporary_url("ops/temporary_url.txt", expiry=60)
