"""TestResponse — wraps httpx.Response with fluent assertion helpers."""

from __future__ import annotations

import json
from typing import Self, cast

import httpx


class TestResponse:
    """Fluent wrapper around an HTTP response — Laravel-style assertions."""

    # Pytest auto-collects classes starting with `Test`; this one isn't a test.
    __test__ = False

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

    def assert_exact_json(self, expected: dict[str, object]) -> Self:
        """Assert the response body equals ``expected`` exactly (alias of ``assert_json``)."""
        return self.assert_json(expected)

    def assert_json_fragment(self, fragment: dict[str, object]) -> Self:
        """Assert every key/value in ``fragment`` appears at the root of the JSON body."""
        actual = self.json()
        if not isinstance(actual, dict):
            raise AssertionError(f"expected JSON object, got {type(actual).__name__}")
        body = cast("dict[str, object]", actual)
        for key, value in fragment.items():
            if key not in body:
                raise AssertionError(f"json fragment missing key {key!r}")
            if body[key] != value:
                raise AssertionError(
                    f"json fragment {key!r}: expected {value!r}, got {body[key]!r}"
                )
        return self

    def assert_json_missing(self, path: str) -> Self:
        """Assert the dotted ``path`` is NOT present in the JSON body."""
        cursor: object = self.json()
        for part in path.split("."):
            if isinstance(cursor, dict):
                mapping = cast("dict[object, object]", cursor)
                if part not in mapping:
                    return self
                cursor = mapping[part]
            elif isinstance(cursor, list):
                items = cast("list[object]", cursor)
                try:
                    cursor = items[int(part)]
                except ValueError, IndexError:
                    return self
            else:
                return self
        raise AssertionError(f"json path {path!r} should be absent, found {cursor!r}")

    def assert_json_structure(self, structure: list[object]) -> Self:
        """Assert the JSON body has the shape described by ``structure``.

        ``structure`` is a list of keys to check at the top level. Nested
        objects use ``{key: [inner_keys...]}`` entries; list-of-objects use
        ``{"*": [inner_keys...]}`` to apply ``inner_keys`` to every element.

        Example::

            response.assert_json_structure([
                "id",
                "name",
                {"profile": ["bio", "avatar"]},
                {"posts": [{"*": ["id", "title"]}]},
            ])
        """
        _check_structure(self.json(), structure)
        return self

    def assert_json_count(self, count: int, path: str | None = None) -> Self:
        """Assert the JSON body (or the value at ``path``) is a list of ``count`` items."""
        target: object = self.json()
        if path is not None:
            for part in path.split("."):
                if isinstance(target, dict):
                    mapping = cast("dict[object, object]", target)
                    if part not in mapping:
                        raise AssertionError(f"json path {path!r} not found at {part!r}")
                    target = mapping[part]
                elif isinstance(target, list):
                    items = cast("list[object]", target)
                    try:
                        target = items[int(part)]
                    except (ValueError, IndexError) as e:
                        raise AssertionError(f"json path {path!r} not found ({e})") from None
                else:
                    raise AssertionError(f"json path {path!r} not traversable at {part!r}")
        if not isinstance(target, list):
            raise AssertionError(f"expected list at {path or '.'}, got {type(target).__name__}")
        items_list = cast("list[object]", target)
        if len(items_list) != count:
            raise AssertionError(f"expected {count} items at {path or '.'}, got {len(items_list)}")
        return self

    def assert_json_validation_errors(self, *fields: str) -> Self:
        """Assert a 422 response carries validation errors for every named field.

        Recognises both the FastAPI/RFC-7807 ``detail`` array shape and the
        Laravel ``errors`` map shape, so tests don't need to know which the
        endpoint emits.
        """
        if self._r.status_code != 422:
            raise AssertionError(f"expected 422 for validation errors, got {self._r.status_code}")
        body = self.json()
        actual_fields = _extract_error_fields(body)
        missing = [f for f in fields if f not in actual_fields]
        if missing:
            raise AssertionError(
                f"expected validation errors for {list(fields)!r}, "
                f"missing {missing!r} (got {sorted(actual_fields)!r})"
            )
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


def _check_list_child(items_list: list[object], sub_structure: list[object]) -> None:
    """Validate every element in a list against ``sub_structure``.

    `{"*": [...]}` as the first sub-structure element means "apply [...] to each item".
    Otherwise sub_structure itself is the per-element shape.
    """
    if sub_structure and isinstance(sub_structure[0], dict):
        wildcard = cast("dict[str, list[object]]", sub_structure[0])
        if "*" in wildcard:
            for element in items_list:
                _check_structure(element, wildcard["*"])
            return
    for element in items_list:
        _check_structure(element, sub_structure)


def _check_dict_entry(body: dict[str, object], key: str, sub_structure: list[object]) -> None:
    if key == "*":
        raise AssertionError("json structure '*' wildcard must appear inside a list")
    if key not in body:
        raise AssertionError(f"json structure missing key {key!r}")
    child = body[key]
    if isinstance(child, list):
        _check_list_child(cast("list[object]", child), sub_structure)
    else:
        _check_structure(child, sub_structure)


def _check_structure(value: object, structure: list[object]) -> None:
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object, got {type(value).__name__}")
    body = cast("dict[str, object]", value)
    for item in structure:
        if isinstance(item, str):
            if item not in body:
                raise AssertionError(f"json structure missing key {item!r}")
        elif isinstance(item, dict):
            spec = cast("dict[str, list[object]]", item)
            for key, sub_structure in spec.items():
                _check_dict_entry(body, key, sub_structure)


def _extract_error_fields(body: object) -> set[str]:
    """Extract the set of field names with validation errors.

    Supports both:
      - FastAPI / Pydantic: ``{"detail": [{"loc": ["body", "email"], ...}, ...]}``
      - Laravel-style:      ``{"errors": {"email": [...], "name": [...]}}``
    """
    fields: set[str] = set()
    if isinstance(body, dict):
        mapping = cast("dict[str, object]", body)
        detail = mapping.get("detail")
        if isinstance(detail, list):
            for raw in cast("list[object]", detail):
                if isinstance(raw, dict):
                    entry = cast("dict[str, object]", raw)
                    loc = entry.get("loc")
                    if isinstance(loc, list) and loc:
                        # Skip the prefix ("body" / "query" / "path") if present.
                        loc_items = cast("list[object]", loc)
                        tail = (
                            loc_items[1:]
                            if loc_items[0] in {"body", "query", "path"}
                            else loc_items
                        )
                        fields.add(".".join(str(p) for p in tail))
        errors = mapping.get("errors")
        if isinstance(errors, dict):
            errors_map = cast("dict[str, object]", errors)
            fields.update(errors_map.keys())
    return fields


__all__ = ["TestResponse"]
