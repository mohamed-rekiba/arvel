"""Tests for S3Driver

The ``TestS3DriverOps`` suite exercises real put/get/exists/delete/temporary_url
against a ``motoserver/moto`` container booted by the session-scoped
:func:`s3_endpoint` fixture (see
``packages/arvel/tests/integration/emulators/fixtures.py``).
The ``TestS3DriverImportError`` suite stays as a pure unit test — it only
verifies the helpful error message when ``arvel[s3]`` isn't installed.

Credentials reach the driver exclusively through ``S3Config`` — the moto
endpoint accepts any non-empty key/secret pair, so the integration suite
configures both via the typed config and verifies the end-to-end wire.
"""

from __future__ import annotations

import sys
from typing import Protocol

import pytest
import pytest_asyncio
from pydantic import SecretStr

aioboto3 = pytest.importorskip("aioboto3", reason="arvel[s3] not installed")

from arvel.config.storage_config import S3Config  # noqa: E402
from arvel.storage.drivers.s3 import S3Driver  # noqa: E402


class S3Endpoint(Protocol):
    """Structural type for the ``s3_endpoint`` fixture (see emulators/fixtures.py).

    Declared inline instead of imported so the test stays self-contained and
    mypy doesn't have to resolve cross-directory test imports.
    """

    url: str
    region: str
    access_key: str
    secret_key: str
    bucket: str


class TestS3DriverImportError:
    def test_helpful_import_error_without_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """helpful ImportError when arvel[s3] not installed.

        Pinning ``sys.modules["aioboto3"] = None`` is the documented way to
        make Python's import machinery treat a package as unavailable, even
        when it's installed on disk.
        """
        monkeypatch.setitem(sys.modules, "aioboto3", None)

        with pytest.raises(ImportError, match=r"arvel\[s3\]"):
            S3Driver(
                config=S3Config(
                    key=SecretStr(""),
                    secret=SecretStr(""),
                    region="us-east-1",
                    bucket="b",
                )
            )


@pytest.mark.requires_emulator
@pytest.mark.integration
class TestS3DriverOps:
    @pytest_asyncio.fixture
    async def driver(self, s3_endpoint: S3Endpoint) -> S3Driver:
        return S3Driver(
            config=S3Config(
                key=SecretStr(s3_endpoint.access_key),
                secret=SecretStr(s3_endpoint.secret_key),
                region=s3_endpoint.region,
                bucket=s3_endpoint.bucket,
                endpoint=s3_endpoint.url,
                addressing_style="path",
            )
        )

    async def test_put_and_get(self, driver: S3Driver) -> None:
        assert await driver.put("ops/put_and_get.txt", b"hello world") is True
        assert await driver.get("ops/put_and_get.txt") == b"hello world"

    async def test_exists(self, driver: S3Driver) -> None:
        assert await driver.exists("ops/exists.txt") is False
        await driver.put("ops/exists.txt", b"x")
        assert await driver.exists("ops/exists.txt") is True

    async def test_delete(self, driver: S3Driver) -> None:
        await driver.put("ops/delete.txt", b"x")
        assert await driver.exists("ops/delete.txt") is True
        assert await driver.delete("ops/delete.txt") is True
        assert await driver.exists("ops/delete.txt") is False

    async def test_temporary_url_returns_signed_url(
        self, driver: S3Driver, s3_endpoint: S3Endpoint
    ) -> None:
        """``temporary_url`` returns a SigV4 pre-signed GET URL.

        Asserts on the canonical SigV4 query parameters (``X-Amz-Signature``,
        ``X-Amz-Expires``) rather than round-tripping to moto, because the
        signing operation is local and that's what we want to verify.
        """
        url = driver.temporary_url("ops/temporary_url.txt", expiry=60)

        assert url.startswith(f"{s3_endpoint.url}/{s3_endpoint.bucket}/")
        assert "X-Amz-Signature=" in url
        assert "X-Amz-Expires=60" in url
