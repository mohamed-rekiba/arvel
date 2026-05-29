"""TestResponse — wraps httpx.Response with fluent assertion helpers."""

from __future__ import annotations

import json
from typing import Self, cast

import httpx


class TestResponse:
    """Fluent wrapper around an HTTP response — Laravel-style assertions."""

    def __init__(self, response: httpx.Response) -> None:
        self._r = response

    @property
    def raw(self) -> httpx.Response:
        return self._r

    @property
    def status_code(self) -> int:
        return self._r.status_code

    def json(self) -> object:
        return json.loads(self._r.content) if self._r.content else None

    def assert_ok(self) -> Self:
        if not (200 <= self._r.status_code < 300):
            raise AssertionError(f"expected 2xx, got {self._r.status_code}: {self._r.text[:200]}")
        return self

    def assert_status(self, code: int) -> Self:
        if self._r.status_code != code:
            raise AssertionError(f"expected status {code}, got {self._r.status_code}")
        return self

    def assert_unauthorized(self) -> Self:
        return self.assert_status(401)

    def assert_forbidden(self) -> Self:
        return self.assert_status(403)

    def assert_not_found(self) -> Self:
        return self.assert_status(404)

    def assert_redirect(self, to: str | None = None) -> Self:
        if not (300 <= self._r.status_code < 400):
            raise AssertionError(f"expected 3xx redirect, got {self._r.status_code}")
        if to is not None:
            actual = self._r.headers.get("Location")
            if actual != to:
                raise AssertionError(f"expected redirect to {to!r}, got {actual!r}")
        return self

    def assert_json(self, expected: dict[str, object]) -> Self:
        actual = self.json()
        if actual != expected:
            raise AssertionError(f"json mismatch: expected {expected!r}, got {actual!r}")
        return self

    def assert_json_path(self, path: str, value: object) -> Self:
        cursor: object = self.json()
        for part in path.split("."):
            if isinstance(cursor, list):
                items = cast("list[object]", cursor)
                try:
                    cursor = items[int(part)]
                except (ValueError, IndexError) as e:
                    raise AssertionError(f"json path {path!r} not found ({e})") from None
            elif isinstance(cursor, dict):
                mapping = cast("dict[object, object]", cursor)
                if part not in mapping:
                    raise AssertionError(f"json path {path!r} not found at {part!r}")
                cursor = mapping[part]
            else:
                raise AssertionError(f"json path {path!r} not found (non-traversable at {part!r})")
        if cursor != value:
            raise AssertionError(f"json path {path!r}: expected {value!r}, got {cursor!r}")
        return self

    def assert_header(self, name: str, value: str | None = None) -> Self:
        if name not in self._r.headers:
            raise AssertionError(f"header {name!r} not present in response")
        if value is not None and self._r.headers[name] != value:
            raise AssertionError(
                f"header {name!r}: expected {value!r}, got {self._r.headers[name]!r}"
            )
        return self

    def assert_cookie(self, name: str) -> Self:
        if name not in self._r.cookies:
            raise AssertionError(f"cookie {name!r} not present in response")
        return self


__all__ = ["TestResponse"]
