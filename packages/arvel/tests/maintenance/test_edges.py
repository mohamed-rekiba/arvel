"""Maintenance mode edge paths."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol, cast

from arvel.maintenance import middleware as middleware_module
from arvel.maintenance.manager import MaintenanceModeManager


class _Send503(Protocol):
    def __call__(
        self,
        instance: object,
        send: Callable[[dict[str, object]], Awaitable[None]],
        *,
        retry: int | None,
        refresh: int | None,
        template: str | None,
    ) -> Awaitable[None]: ...


def test_maintenance_manager_handles_missing_and_corrupt_markers(tmp_path: Path) -> None:
    marker = tmp_path / "down"
    manager = MaintenanceModeManager(marker)

    assert manager.marker_path == marker
    assert manager.is_down() is False
    assert manager.read_marker() is None

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{not-json")
    assert manager.is_down() is True
    assert manager.read_marker() is None


def test_maintenance_manager_writes_reads_and_removes_marker(tmp_path: Path) -> None:
    manager = MaintenanceModeManager(tmp_path / "down")

    written = manager.down(secret="open-sesame", retry=30, refresh=60, template="down.html")
    read = manager.read_marker()

    assert read == written
    assert read is not None
    assert read.secret == "open-sesame"
    manager.up()
    manager.up()
    assert manager.is_down() is False


def test_parse_cookies_ignores_malformed_pairs() -> None:
    parse_cookies = cast(
        "Callable[[dict[str, object]], dict[str, str]]",
        object.__getattribute__(middleware_module, "_parse_cookies"),
    )

    assert parse_cookies({"headers": [(b"cookie", b"bad; arvel_bypass=secret")]}) == {
        "arvel_bypass": "secret"
    }
    assert parse_cookies({"headers": []}) == {}


def test_maintenance_middleware_cookie_and_query_helpers() -> None:
    has_valid_cookie = cast(
        "Callable[[dict[str, object], str], bool]",
        object.__getattribute__(middleware_module.MaintenanceModeMiddleware, "_has_valid_cookie"),
    )
    extract_query = cast(
        "Callable[[dict[str, object]], str | None]",
        object.__getattribute__(
            middleware_module.MaintenanceModeMiddleware,
            "_extract_query_bypass",
        ),
    )

    assert has_valid_cookie({"headers": [(b"cookie", b"arvel_bypass=secret")]}, "secret") is True
    assert has_valid_cookie({"headers": [(b"cookie", b"arvel_bypass=bad")]}, "secret") is False
    assert extract_query({"query_string": b"bypass=secret"}) == "secret"
    assert extract_query({"query_string": b""}) is None
    assert extract_query({"query_string": "not-bytes"}) is None


async def test_maintenance_middleware_sends_503_headers() -> None:
    send_503 = cast(
        "_Send503",
        object.__getattribute__(middleware_module.MaintenanceModeMiddleware, "_send_503"),
    )
    empty_receive = cast(
        "Callable[[], Awaitable[dict[str, object]]]",
        object.__getattribute__(middleware_module, "_empty_receive"),
    )
    messages: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    middleware = object.__new__(middleware_module.MaintenanceModeMiddleware)
    await send_503(middleware, send, retry=30, refresh=60, template=None)

    assert await empty_receive() == {"type": "http.disconnect"}
    assert messages[0]["type"] == "http.response.start"
    headers = dict(cast("list[tuple[bytes, bytes]]", messages[0]["headers"]))
    assert headers[b"retry-after"] == b"30"
    assert headers[b"refresh"] == b"60"
    assert headers[b"cache-control"] == b"no-store"


async def test_maintenance_middleware_renders_template_when_set(tmp_path: Path) -> None:
    """`--render <path>` swaps the plain-text body for the rendered template."""
    send_503 = cast(
        "_Send503",
        object.__getattribute__(middleware_module.MaintenanceModeMiddleware, "_send_503"),
    )
    template_path = tmp_path / "down.html"
    template_path.write_text("<h1>Custom maintenance page</h1>", encoding="utf-8")

    bodies: list[bytes] = []

    async def send(message: dict[str, object]) -> None:
        if message["type"] == "http.response.body":
            bodies.append(cast("bytes", message.get("body", b"")))

    middleware = object.__new__(middleware_module.MaintenanceModeMiddleware)
    await send_503(middleware, send, retry=None, refresh=None, template=str(template_path))

    assert any(b"Custom maintenance page" in body for body in bodies)


async def test_maintenance_middleware_falls_back_when_template_missing(tmp_path: Path) -> None:
    """A configured template that can't be read is logged and downgraded to plain text."""
    send_503 = cast(
        "_Send503",
        object.__getattribute__(middleware_module.MaintenanceModeMiddleware, "_send_503"),
    )
    missing = tmp_path / "does-not-exist.html"

    bodies: list[bytes] = []

    async def send(message: dict[str, object]) -> None:
        if message["type"] == "http.response.body":
            bodies.append(cast("bytes", message.get("body", b"")))

    middleware = object.__new__(middleware_module.MaintenanceModeMiddleware)
    await send_503(middleware, send, retry=None, refresh=None, template=str(missing))

    assert any(b"App is down for maintenance." in body for body in bodies)
