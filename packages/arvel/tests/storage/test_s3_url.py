"""Unit tests for ``S3Driver.url()`` — covers the three URL-resolution modes.

``url()`` doesn't talk to S3 — it builds a public URL from configuration —
so these tests run without an emulator and without the network. They lock
in the priority order: ``public_url`` (CDN / custom domain) →
``endpoint`` (path-style off the API endpoint) → AWS hostname pattern.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

pytest.importorskip("aioboto3", reason="arvel[s3] not installed")
pytest.importorskip("boto3", reason="arvel[s3] not installed")

from arvel.config.storage_config import S3Config
from arvel.storage.drivers.s3 import S3Driver


def _driver(**config_overrides: object) -> S3Driver:
    base: dict[str, object] = {
        "key": SecretStr("k"),
        "secret": SecretStr("s"),
        "region": "us-east-1",
        "bucket": "my-bucket",
    }
    base.update(config_overrides)
    return S3Driver(config=S3Config(**base))  # type: ignore[arg-type]


class TestS3DriverUrl:
    """Verifies the three-tier URL priority documented on ``S3Driver.url``."""

    def test_falls_back_to_aws_hostname_when_no_endpoint(self) -> None:
        driver = _driver()

        assert driver.url("photos/cat.jpg") == (
            "https://my-bucket.s3.us-east-1.amazonaws.com/photos/cat.jpg"
        )

    def test_falls_back_to_aws_hostname_honors_region(self) -> None:
        driver = _driver(region="eu-west-2")

        assert driver.url("a.txt") == "https://my-bucket.s3.eu-west-2.amazonaws.com/a.txt"

    def test_endpoint_set_uses_path_style(self) -> None:
        """MinIO / Hetzner / B2 — endpoint set, no custom domain → path-style."""
        driver = _driver(endpoint="https://s3.example.com")

        assert driver.url("photos/cat.jpg") == "https://s3.example.com/my-bucket/photos/cat.jpg"

    def test_endpoint_set_strips_trailing_slash(self) -> None:
        driver = _driver(endpoint="https://s3.example.com/")

        assert driver.url("a.txt") == "https://s3.example.com/my-bucket/a.txt"

    def test_public_url_wins_over_endpoint(self) -> None:
        """R2 with a custom domain — public_url overrides endpoint."""
        driver = _driver(
            endpoint="https://abc.r2.cloudflarestorage.com",
            public_url="https://cdn.example.com",
        )

        assert driver.url("photos/cat.jpg") == "https://cdn.example.com/photos/cat.jpg"

    def test_public_url_strips_trailing_slash(self) -> None:
        driver = _driver(public_url="https://cdn.example.com/")

        assert driver.url("a.txt") == "https://cdn.example.com/a.txt"

    def test_url_honors_prefix(self) -> None:
        driver = S3Driver(
            config=S3Config(
                key=SecretStr("k"),
                secret=SecretStr("s"),
                region="us-east-1",
                bucket="my-bucket",
                endpoint="https://s3.example.com",
            ),
            prefix="tenant-a/",
        )

        assert driver.url("photos/cat.jpg") == (
            "https://s3.example.com/my-bucket/tenant-a/photos/cat.jpg"
        )
