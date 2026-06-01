"""Tests for AzureDriver

The ``TestAzureDriverOps`` suite exercises real put/get/exists/delete against
an ``mcr.microsoft.com/azure-storage/azurite`` container booted by the
session-scoped :func:`azurite_endpoint` fixture (see
``packages/arvel/tests/integration/emulators/fixtures.py``).
The ``TestAzureDriverImportError`` suite stays as a pure unit test — it only
verifies the helpful error message when ``arvel[azure]`` isn't installed.
"""

from __future__ import annotations

import sys
from typing import Protocol

import pytest
import pytest_asyncio
from pydantic import SecretStr

azure_storage_blob = pytest.importorskip("azure.storage.blob", reason="arvel[azure] not installed")

from arvel.config.storage_config import AzureConfig  # noqa: E402
from arvel.storage.drivers.azure import AzureDriver  # noqa: E402


class AzuriteEndpoint(Protocol):
    """Structural type for the ``azurite_endpoint`` fixture (see emulators/fixtures.py).

    Declared inline instead of imported so the test stays self-contained and
    mypy doesn't have to resolve cross-directory test imports.
    """

    connection_string: str
    account: str
    key: str
    container: str
    blob_endpoint: str


class TestAzureDriverImportError:
    def test_helpful_import_error_without_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """helpful ImportError when arvel[azure] not installed.

        Pinning ``sys.modules["azure.storage.blob.aio"] = None`` is the
        documented way to make Python's import machinery treat a package as
        unavailable, even when it's installed on disk. The driver imports
        the ``.aio`` submodule, so that's the entry to block.
        """
        monkeypatch.setitem(sys.modules, "azure.storage.blob.aio", None)

        with pytest.raises(ImportError, match=r"arvel\[azure\]"):
            AzureDriver(config=AzureConfig(account="a", key=SecretStr("k"), container="c"))


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestAzureDriverOps:
    @pytest_asyncio.fixture
    async def driver(self, azurite_endpoint: AzuriteEndpoint) -> AzureDriver:
        # AzureConfig's account-based URL hardcodes the real Azure DNS suffix
        # (``*.blob.core.windows.net``), so we bypass it and bind directly via
        # the Azurite connection string — the same pattern real Azurite users
        # follow during local development.
        return AzureDriver(
            container=azurite_endpoint.container,
            connection_string=azurite_endpoint.connection_string,
        )

    async def test_put_and_get(self, driver: AzureDriver) -> None:
        # Single round-trip the four core operations against Azurite:
        # absence → put → exists → get → delete → absence.
        assert await driver.exists("ops/put_and_get.txt") is False
        assert await driver.put("ops/put_and_get.txt", b"hello azurite") is True
        assert await driver.exists("ops/put_and_get.txt") is True
        assert await driver.get("ops/put_and_get.txt") == b"hello azurite"
        assert await driver.delete("ops/put_and_get.txt") is True
        assert await driver.exists("ops/put_and_get.txt") is False

    async def test_temporary_url(self, driver: AzureDriver) -> None:
        # AzureDriver.temporary_url would need a SAS token generator; the
        # driver documents this as NotImplementedError for now. The contract
        # is verified without round-tripping to Azurite.
        with pytest.raises(NotImplementedError, match="SAS token"):
            driver.temporary_url("ops/temporary_url.txt", expiry=60)
