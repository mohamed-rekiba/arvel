"""C5b — named-route URL generation + signed / temporary-signed URLs."""

from __future__ import annotations

import time
from typing import Any

from arvel.routing import Router

KEY = "test-secret-key"


def _router() -> Router:
    router = Router()
    router.get("/posts/{post}", lambda request, post: {}, name="posts.show")
    return router


def _noop(request: Any, post: Any) -> dict[str, Any]:
    return {}


def test_named_url_generation() -> None:
    assert _router().url("posts.show", post=7) == "/posts/7"


def test_signed_url_is_valid() -> None:
    router = _router()
    signed = router.signed_url("posts.show", key=KEY, post=7)
    assert "signature=" in signed
    assert router.has_valid_signature(signed, key=KEY)


def test_tampered_url_is_rejected() -> None:
    router = _router()
    signed = router.signed_url("posts.show", key=KEY, post=7)
    tampered = signed.replace("/posts/7", "/posts/8")
    assert not router.has_valid_signature(tampered, key=KEY)


def test_wrong_key_is_rejected() -> None:
    router = _router()
    signed = router.signed_url("posts.show", key=KEY, post=7)
    assert not router.has_valid_signature(signed, key="different-key")


def test_temporary_signed_url_expired() -> None:
    router = _router()
    past = int(time.time()) - 10
    signed = router.signed_url("posts.show", key=KEY, expires=past, post=7)
    assert not router.has_valid_signature(signed, key=KEY)


def test_temporary_signed_url_still_valid() -> None:
    router = _router()
    future = int(time.time()) + 3600
    signed = router.signed_url("posts.show", key=KEY, expires=future, post=7)
    assert router.has_valid_signature(signed, key=KEY)
