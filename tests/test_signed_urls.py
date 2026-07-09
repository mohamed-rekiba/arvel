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


# --- S3 (DR-0047): byte-identical base reconstruction ------------------------------------


def test_signature_in_query_value_verifies_correctly() -> None:
    """A query *value* that literally contains ``signature=`` (e.g. a ``next`` redirect param)
    must not confuse the base/token boundary — the split is on the ``&``-segment, not a raw
    substring search."""
    from arvel.security import Signer

    url = "/posts/7?next=/x?signature=abc"
    token = Signer(KEY).sign(url)
    signed = url + "&signature=" + token
    router = _router()
    assert router.has_valid_signature(signed, key=KEY)


def test_injected_extra_signature_param_is_rejected() -> None:
    """Two ``signature=`` params (an attacker-injected fake ahead of the real, trailing one):
    only the trailing segment is the boundary, so the fake stays in the reconstructed base and
    the re-sign mismatches — fail closed."""
    router = _router()
    signed = router.signed_url("posts.show", key=KEY, post=7)
    base, real_signature = signed.split("signature=", 1)
    tampered = f"{base}signature=fake&signature={real_signature}"
    assert not router.has_valid_signature(tampered, key=KEY)


def test_no_signature_param_is_rejected() -> None:
    router = _router()
    assert not router.has_valid_signature("/posts/7", key=KEY)


def test_malformed_expires_is_rejected() -> None:
    """A non-integer ``expires=`` value fails closed (the ``int()`` guard is a scoped
    ``except ValueError``, never a bare-``Exception`` swallow)."""
    from arvel.security import Signer

    url = "/posts/7?expires=not-a-number"
    token = Signer(KEY).sign(url)
    signed = url + "&signature=" + token
    router = _router()
    assert not router.has_valid_signature(signed, key=KEY)


def test_malformed_url_fails_closed_not_raises() -> None:
    # a signature verifier must never propagate a parse error — a malformed host
    # (invalid IPv6) once raised ValueError from urlsplit; it must fail closed instead
    for bad in ("//[::1?signature=x", "http://[::1?signature=abc"):
        assert _router().has_valid_signature(bad, key=KEY) is False
