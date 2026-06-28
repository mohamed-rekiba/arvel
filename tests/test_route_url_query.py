"""R3 — named-route url() query-param handling (Laravel route()): extra params become a
query string; a missing required path param raises. Grounded in arvel-correctness-review R3."""

from __future__ import annotations

import pytest

from arvel.routing import Router


def _router() -> Router:
    router = Router()
    router.get("/users/{id}", lambda: None, name="user.show")
    return router


def test_extra_param_becomes_query_string() -> None:  # AC1
    assert _router().url("user.show", id=7, tab="profile") == "/users/7?tab=profile"


def test_multiple_extras_encoded_and_joined() -> None:  # AC2
    url = _router().url("user.show", id=1, q="a b", page=2)
    assert url == "/users/1?q=a+b&page=2"


def test_missing_required_param_raises() -> None:  # AC3
    with pytest.raises(ValueError, match="id"):
        _router().url("user.show")


def test_unknown_route_raises_keyerror() -> None:  # AC4
    with pytest.raises(KeyError):
        _router().url("nope")


def test_path_only_is_unchanged() -> None:  # AC5
    assert _router().url("user.show", id=7) == "/users/7"


def test_signed_url_still_round_trips_with_query() -> None:  # AC5
    router = _router()
    signed = router.signed_url("user.show", key="secret", id=7, tab="x")
    assert "tab=x" in signed
    assert router.has_valid_signature(signed, key="secret")
