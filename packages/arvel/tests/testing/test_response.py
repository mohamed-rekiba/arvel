"""Tests for arvel.testing.TestResponse."""

from __future__ import annotations

import httpx
import pytest


def _make(
    content: bytes, status: int = 200, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status_code=status, content=content, headers=headers)


class TestStatusAssertions:
    def test_assert_ok_passes_on_2xx(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"ok": true}', 200))
        r.assert_ok()
        r2 = TestResponse(_make(b"", 204))
        r2.assert_ok()

    def test_assert_ok_fails_on_4xx(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b"", 400))
        with pytest.raises(AssertionError, match="2xx"):
            r.assert_ok()

    def test_assert_status_exact(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b"", 201))
        r.assert_status(201)
        with pytest.raises(AssertionError):
            r.assert_status(200)

    def test_assert_unauthorized(self) -> None:
        from arvel.testing import TestResponse

        TestResponse(_make(b"", 401)).assert_unauthorized()
        with pytest.raises(AssertionError):
            TestResponse(_make(b"", 403)).assert_unauthorized()

    def test_assert_forbidden(self) -> None:
        from arvel.testing import TestResponse

        TestResponse(_make(b"", 403)).assert_forbidden()

    def test_assert_not_found(self) -> None:
        from arvel.testing import TestResponse

        TestResponse(_make(b"", 404)).assert_not_found()


class TestJsonAssertions:
    def test_assert_json_full_match(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"name": "alice", "age": 30}'))
        r.assert_json({"name": "alice", "age": 30})

    def test_assert_json_fails_on_mismatch(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"name": "alice"}'))
        with pytest.raises(AssertionError):
            r.assert_json({"name": "bob"})

    def test_assert_json_path_simple(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"user": {"id": 42}}'))
        r.assert_json_path("user.id", 42)

    def test_assert_json_path_array_index(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"items": [{"k": "a"}, {"k": "b"}]}'))
        r.assert_json_path("items.0.k", "a")
        r.assert_json_path("items.1.k", "b")

    def test_assert_json_path_missing_raises(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b"{}"))
        with pytest.raises(AssertionError, match="not found"):
            r.assert_json_path("nope.gone", "x")


class TestHeaderAssertions:
    def test_assert_header(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b"", headers={"X-Custom": "ok"}))
        r.assert_header("X-Custom", "ok")

    def test_assert_header_present_only(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b"", headers={"X-Custom": "ok"}))
        r.assert_header("X-Custom")  # no value = just presence

    def test_assert_header_fails_when_absent(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b""))
        with pytest.raises(AssertionError):
            r.assert_header("X-Missing")


class TestRedirectAssertions:
    def test_assert_redirect_to(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b"", 302, headers={"Location": "/login"}))
        r.assert_redirect("/login")

    def test_assert_redirect_without_target_just_checks_3xx(self) -> None:
        from arvel.testing import TestResponse

        TestResponse(_make(b"", 301)).assert_redirect()
        TestResponse(_make(b"", 302, headers={"Location": "/x"})).assert_redirect()


class TestChaining:
    def test_assertions_return_self_for_chaining(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"ok": true}', 200))
        result = r.assert_ok().assert_json({"ok": True})
        assert result is r
