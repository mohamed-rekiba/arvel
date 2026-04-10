"""Auto-skip fixtures for integration tests that require live services.

When a test is marked with a service marker (e.g. ``@pytest.mark.redis``)
and the service is unavailable, the test is skipped with a clear message
instead of failing. In CI with all services running, nothing is skipped.
"""

from __future__ import annotations

import socket

import pytest

pytestmark = pytest.mark.integration


def _can_connect(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _skip_without_service(request: pytest.FixtureRequest) -> None:
    """Skip tests when their required service is unavailable."""
    service_checks: dict[str, tuple[str, int]] = {
        "redis": ("localhost", 6379),
        "smtp": ("localhost", 1025),
        "s3": ("localhost", 9000),
        "rabbitmq": ("localhost", 5672),
        "oidc": ("localhost", 8080),
        "pg_only": ("localhost", 5432),
        "mysql_only": ("localhost", 3306),
    }
    for marker_name, (host, port) in service_checks.items():
        if request.node.get_closest_marker(marker_name) and not _can_connect(host, port):
            pytest.skip(f"{marker_name} not available at {host}:{port}")
