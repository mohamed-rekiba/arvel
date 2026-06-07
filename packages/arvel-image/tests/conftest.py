"""Test fixtures for arvel-image.

Inherits engine/session fixtures from the workspace-root conftest.py — only
defines fixtures that are specific to arvel-image's integration suite.

MinIO fixtures are copied from ``kits/arvel-ecommerce-kit/backend/tests/
conftest.py`` (Rule of Three — two callers is premature abstraction). If a
third caller appears or this fixture grows significantly, extract to
``arvel.testing.s3``. Keep this file's MinIO image pin in sync with the kit's.
"""

from __future__ import annotations

import contextlib
import importlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

# Keep this pin in sync with kits/arvel-ecommerce-kit/backend/tests/conftest.py.
# Bump via web search — verify the exact tag exists on Docker Hub
# (`docker manifest inspect <image>`) before committing. Don't assume
# minio/minio and minio/mc share the same RELEASE date; they cut releases
# independently.
IMAGE_MINIO = "minio/minio:RELEASE.2025-09-07T16-13-09Z"  # web-verified 2026-06-04

_MINIO_ROOT_USER = "minioadmin"
_MINIO_ROOT_PASSWORD = "minioadmin"  # well-known test credential; container is local-only


@dataclass(frozen=True)
class MinioEndpoint:
    """Connection info for the session-scoped MinIO container."""

    endpoint_url: str
    region: str
    access_key: str
    secret_key: str
    bucket: str


def _docker_available() -> bool:
    try:
        docker_mod: Any = importlib.import_module("docker")
        client: Any = docker_mod.from_env()
        client.ping()
    except Exception:
        return False
    return True


def _skip_if_no_docker() -> None:
    if not _docker_available():
        pytest.skip(
            "Docker daemon unreachable; install Docker to run the testcontainers harness",
            allow_module_level=False,
        )


def _docker_container(image: str, *, ready_log: str, timeout: int = 120) -> Any:
    tc_container: Any = importlib.import_module("testcontainers.core.container")
    tc_strategies: Any = importlib.import_module("testcontainers.core.wait_strategies")
    container = tc_container.DockerContainer(image)
    strategy = tc_strategies.LogMessageWaitStrategy(ready_log).with_startup_timeout(timeout)
    container.waiting_for(strategy)
    return container


@pytest.fixture(scope="session")
def minio_endpoint() -> Iterator[MinioEndpoint]:
    _skip_if_no_docker()
    bucket = "arvel-image-tests"
    container = _docker_container(IMAGE_MINIO, ready_log=r"API: http://")
    container.with_command("server /data --console-address :9001")
    container.with_env("MINIO_ROOT_USER", _MINIO_ROOT_USER)
    container.with_env("MINIO_ROOT_PASSWORD", _MINIO_ROOT_PASSWORD)
    container.with_exposed_ports(9000, 9001)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: int = int(container.get_exposed_port(9000))
        endpoint_url = f"http://{host}:{port}"
        boto3: Any = importlib.import_module("boto3")
        client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name="us-east-1",
            aws_access_key_id=_MINIO_ROOT_USER,
            aws_secret_access_key=_MINIO_ROOT_PASSWORD,
        )
        client.create_bucket(Bucket=bucket)
        yield MinioEndpoint(
            endpoint_url=endpoint_url,
            region="us-east-1",
            access_key=_MINIO_ROOT_USER,
            secret_key=_MINIO_ROOT_PASSWORD,
            bucket=bucket,
        )
    finally:
        container.stop()


@pytest.fixture
def minio_bucket(minio_endpoint: MinioEndpoint) -> Iterator[str]:
    """Per-test bucket — isolates tests from each other within the session."""
    bucket = f"test-{uuid.uuid4().hex[:8]}"
    boto3: Any = importlib.import_module("boto3")
    client: Any = boto3.client(
        "s3",
        endpoint_url=minio_endpoint.endpoint_url,
        region_name="us-east-1",
        aws_access_key_id=minio_endpoint.access_key,
        aws_secret_access_key=minio_endpoint.secret_key,
    )
    client.create_bucket(Bucket=bucket)
    try:
        yield bucket
    finally:
        # Best-effort cleanup — list and delete all objects, then the bucket.
        # Container teardown reclaims everything anyway; per-bucket cleanup is best-effort.
        with contextlib.suppress(Exception):
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                contents: list[dict[str, Any]] = page.get("Contents") or []
                for obj in contents:
                    client.delete_object(Bucket=bucket, Key=obj["Key"])
            client.delete_bucket(Bucket=bucket)
