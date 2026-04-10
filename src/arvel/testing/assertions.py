"""Fluent HTTP response assertions for TestClient responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import httpx

_MAX_ERROR_LEN = 500


def _truncate(msg: str) -> str:
    return msg[:_MAX_ERROR_LEN] if len(msg) > _MAX_ERROR_LEN else msg


def _resolve_path(data: Any, path: str) -> tuple[bool, Any]:
    """Walk a dot-notation path, treating numeric segments as list indices."""
    segments = path.split(".")
    current = data
    for seg in segments:
        if isinstance(current, dict) and seg in current:
            current = current[seg]
        elif isinstance(current, list) and seg.isdigit():
            idx = int(seg)
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return False, None
        else:
            return False, None
    return True, current


class TestResponse:
    """Wraps ``httpx.Response`` with fluent assertion methods.

    Every ``assert_*`` method returns ``self`` so assertions can be chained::

        response.assert_status(200).assert_json_path("data.name", "Alice")
    """

    __test__ = False

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)

    def assert_status(self, expected: int) -> Self:
        actual = self._response.status_code
        if actual != expected:
            body = self._response.text[:200]
            raise AssertionError(
                _truncate(f"Expected status {expected}, got {actual}. Body: {body}")
            )
        return self

    def assert_ok(self) -> Self:
        return self.assert_status(200)

    def assert_created(self) -> Self:
        return self.assert_status(201)

    def assert_no_content(self) -> Self:
        return self.assert_status(204)

    def assert_not_found(self) -> Self:
        return self.assert_status(404)

    def assert_unprocessable(self) -> Self:
        return self.assert_status(422)

    def assert_json(self, expected: dict[str, Any]) -> Self:
        actual = self._response.json()
        if actual != expected:
            raise AssertionError(
                _truncate(f"JSON body mismatch.\nExpected: {expected}\nActual: {actual}")
            )
        return self

    def assert_json_path(self, path: str, expected: Any) -> Self:
        data = self._response.json()
        found, actual = _resolve_path(data, path)
        if not found:
            raise AssertionError(_truncate(f"Path '{path}' not found in response JSON"))
        if actual != expected:
            raise AssertionError(
                _truncate(f"Expected '{expected}' at path '{path}', got '{actual}'")
            )
        return self

    def assert_json_structure(self, structure: dict[str, Any]) -> Self:
        data = self._response.json()
        self._check_structure(data, structure, prefix="")
        return self

    def _check_structure(self, data: Any, structure: dict[str, Any], *, prefix: str) -> None:
        if not isinstance(data, dict):
            raise AssertionError(
                _truncate(f"Expected dict at '{prefix}', got {type(data).__name__}")
            )
        for key, value in structure.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if key not in data:
                raise AssertionError(_truncate(f"Missing key '{full_key}' in response JSON"))
            if isinstance(value, dict):
                self._check_structure(data[key], value, prefix=full_key)

    def assert_json_missing(self, key: str) -> Self:
        data = self._response.json()
        if isinstance(data, dict) and key in data:
            raise AssertionError(_truncate(f"Key '{key}' should not be present in response JSON"))
        return self

    def assert_redirect(self, url: str | None = None) -> Self:
        status = self._response.status_code
        if not (300 <= status < 400):
            raise AssertionError(_truncate(f"Expected redirect (3xx), got {status}"))
        if url is not None:
            location = self._response.headers.get("location", "")
            if location != url:
                raise AssertionError(_truncate(f"Expected redirect to '{url}', got '{location}'"))
        return self

    def assert_header(self, name: str, value: str | None = None) -> Self:
        actual = self._response.headers.get(name)
        if actual is None:
            raise AssertionError(_truncate(f"Header '{name}' not found in response"))
        if value is not None and actual != value:
            raise AssertionError(_truncate(f"Header '{name}' expected '{value}', got '{actual}'"))
        return self

    def assert_header_missing(self, name: str) -> Self:
        if name.lower() in (k.lower() for k in self._response.headers):
            raise AssertionError(_truncate(f"Header '{name}' should not be present"))
        return self

    def assert_cookie(self, name: str) -> Self:
        jar = self._response.cookies
        if name not in jar:
            raw_header = self._response.headers.get("set-cookie", "")
            if name not in raw_header:
                raise AssertionError(_truncate(f"Cookie '{name}' not found in response"))
        return self
