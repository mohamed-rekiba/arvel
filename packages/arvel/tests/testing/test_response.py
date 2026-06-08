"""Tests for arvel.testing.TestResponse."""

from __future__ import annotations

import httpx2 as httpx
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


class TestExactJsonAndFragment:
    def test_assert_exact_json_passes(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"a": 1, "b": 2}'))
        r.assert_exact_json({"a": 1, "b": 2})

    def test_assert_exact_json_fails_on_extra_key(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"a": 1, "b": 2}'))
        with pytest.raises(AssertionError, match="json mismatch"):
            r.assert_exact_json({"a": 1})

    def test_assert_json_fragment_passes_on_subset(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"name": "alice", "id": 42, "extra": true}'))
        r.assert_json_fragment({"name": "alice"})
        r.assert_json_fragment({"id": 42, "name": "alice"})

    def test_assert_json_fragment_fails_on_missing_key(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"name": "alice"}'))
        with pytest.raises(AssertionError, match="missing key"):
            r.assert_json_fragment({"age": 30})

    def test_assert_json_fragment_fails_on_wrong_value(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"name": "alice"}'))
        with pytest.raises(AssertionError, match="expected 'bob'"):
            r.assert_json_fragment({"name": "bob"})

    def test_assert_json_fragment_fails_on_non_object(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b"[1, 2, 3]"))
        with pytest.raises(AssertionError, match="expected JSON object"):
            r.assert_json_fragment({"name": "alice"})


class TestJsonMissing:
    def test_assert_json_missing_passes_when_absent(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"user": {"id": 42}}'))
        r.assert_json_missing("user.email")
        r.assert_json_missing("nope")

    def test_assert_json_missing_fails_when_present(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"user": {"id": 42}}'))
        with pytest.raises(AssertionError, match="should be absent"):
            r.assert_json_missing("user.id")


class TestJsonStructure:
    def test_assert_json_structure_top_level_keys(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"id": 1, "name": "x", "extra": true}'))
        r.assert_json_structure(["id", "name"])

    def test_assert_json_structure_nested(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"id": 1, "profile": {"bio": "hi", "avatar": "u.png"}}'))
        r.assert_json_structure(["id", {"profile": ["bio", "avatar"]}])

    def test_assert_json_structure_list_wildcard(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"posts": [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]}'))
        r.assert_json_structure([{"posts": [{"*": ["id", "title"]}]}])

    def test_assert_json_structure_missing_key_fails(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"id": 1}'))
        with pytest.raises(AssertionError, match="missing key 'name'"):
            r.assert_json_structure(["id", "name"])


class TestJsonCount:
    def test_assert_json_count_root_array(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b"[1, 2, 3]"))
        r.assert_json_count(3)

    def test_assert_json_count_at_path(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"items": [1, 2]}'))
        r.assert_json_count(2, "items")

    def test_assert_json_count_fails_on_wrong_size(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"items": [1, 2]}'))
        with pytest.raises(AssertionError, match="expected 5 items"):
            r.assert_json_count(5, "items")

    def test_assert_json_count_fails_on_non_list(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"items": 42}'))
        with pytest.raises(AssertionError, match="expected list"):
            r.assert_json_count(1, "items")


class TestJsonValidationErrors:
    def test_recognises_fastapi_detail_shape(self) -> None:
        from arvel.testing import TestResponse

        body = (
            b'{"detail": ['
            b'{"loc": ["body", "email"], "msg": "invalid"}, '
            b'{"loc": ["body", "name"], "msg": "required"}'
            b"]}"
        )
        r = TestResponse(_make(body, status=422))
        r.assert_json_validation_errors("email", "name")

    def test_recognises_laravel_errors_shape(self) -> None:
        from arvel.testing import TestResponse

        body = b'{"errors": {"email": ["invalid"], "name": ["required"]}}'
        r = TestResponse(_make(body, status=422))
        r.assert_json_validation_errors("email")

    def test_fails_when_status_is_not_422(self) -> None:
        from arvel.testing import TestResponse

        r = TestResponse(_make(b'{"detail": []}', status=400))
        with pytest.raises(AssertionError, match="expected 422"):
            r.assert_json_validation_errors("email")

    def test_fails_when_field_is_missing_from_errors(self) -> None:
        from arvel.testing import TestResponse

        body = b'{"errors": {"email": ["invalid"]}}'
        r = TestResponse(_make(body, status=422))
        with pytest.raises(AssertionError, match="missing \\['name'\\]"):
            r.assert_json_validation_errors("email", "name")
