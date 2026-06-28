"""ch04 / finding A1 — ValidatePostSize global middleware: an over-large request body is
rejected with 413 before the handler runs (Laravel ValidatePostSize), and it's wired into the
default global pipeline."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.maintenance import PreventRequestsDuringMaintenance
from arvel.http.middleware import RequestContextMiddleware, ValidatePostSize
from arvel.routing import Router


class _Tiny(ValidatePostSize):
    DEFAULT_MAX = 10  # bytes


async def _ok(request: Any) -> dict[str, str]:
    return {"ok": "1"}


def test_use_default_global_wires_post_size_after_maintenance() -> None:
    kernel = HttpKernel().use_default_global()
    assert kernel.global_middleware[0] is RequestContextMiddleware  # request-id first (M3)
    # maintenance still runs before post-size validation
    assert kernel.global_middleware.index(PreventRequestsDuringMaintenance) < (
        kernel.global_middleware.index(ValidatePostSize)
    )
    assert ValidatePostSize in kernel.global_middleware
    kernel.use_default_global()  # idempotent
    assert kernel.global_middleware.count(ValidatePostSize) == 1


def test_limit_override() -> None:
    assert ValidatePostSize(max_bytes=5)._limit() == 5


def test_over_limit_body_is_413() -> None:
    router = Router()
    router.post("/upload", _ok)
    kernel = HttpKernel()
    kernel.global_middleware.append(_Tiny)
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.post("/upload", content=b"x" * 50).status_code == 413


def test_under_limit_body_passes() -> None:
    router = Router()
    router.post("/upload", _ok)
    kernel = HttpKernel()
    kernel.global_middleware.append(_Tiny)
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        assert client.post("/upload", content=b"hi").json() == {"ok": "1"}
