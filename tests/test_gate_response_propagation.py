"""Gate/policy "deeper" parity: a policy's custom deny **message + status code** survive through
inspect()/authorize() and out to the HTTP response (previously discarded → denials rendered a
generic 500), plus policy-level before() (super-admin auto-grant). Gate/AuthorizationException."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from arvel.auth.gate import AuthorizationError, Gate, GateResponse


@dataclass
class User:
    id: int
    admin: bool = False


class Post:
    pass


class PostPolicy:
    def before(self, user: User, ability: str) -> bool | None:
        return True if user.admin else None  # super-admin passes everything; else fall through

    def update(self, user: User, post: Post) -> GateResponse:
        return GateResponse.deny("You don't own this post.", code=403)

    def view(self, user: User, post: Post) -> GateResponse:
        return GateResponse.deny_as_not_found()  # hide existence → 404


def _gate() -> Gate:
    g = Gate()
    g.policy(Post, PostPolicy)
    return g


async def test_inspect_preserves_policy_deny_message_and_code() -> None:
    resp = await _gate().inspect("update", Post(), user=User(1))
    assert isinstance(resp, GateResponse)
    assert bool(resp) is False
    assert resp.message == "You don't own this post."  # custom message preserved (not generic)
    assert resp.code == 403


async def test_authorize_carries_message_and_status() -> None:
    with pytest.raises(AuthorizationError) as ei:
        await _gate().authorize("update", Post(), user=User(1))
    err = ei.value
    assert err.detail == "You don't own this post."  # message threaded to the exception
    assert err.status == 403


async def test_deny_as_not_found_yields_404() -> None:
    with pytest.raises(AuthorizationError) as ei:
        await _gate().authorize("view", Post(), user=User(1))
    assert ei.value.status == 404  # hides existence


async def test_policy_before_grants_super_admin_and_falls_through() -> None:
    gate = _gate()
    # admin: policy.before returns True → granted without consulting update() (which would deny)
    assert await gate.allows("update", Post(), user=User(1, admin=True)) is True
    # non-admin: before returns None → falls through to update() → denied
    assert await gate.allows("update", Post(), user=User(2)) is False


def test_authorization_error_renders_correct_status_and_message() -> None:
    """The HTTP renderer maps AuthorizationError.status/.detail → the response; previously it had
    no .status and rendered as a generic 500."""
    from arvel.http.exceptions import render_exception

    class _Req:
        headers = {"accept": "application/json"}

    forbidden = render_exception(_Req(), AuthorizationError("update", "You don't own this post."))
    assert forbidden.status_code == 403
    assert forbidden.content["message"] == "You don't own this post."

    not_found = render_exception(_Req(), AuthorizationError("view", "Not Found", code=404))
    assert not_found.status_code == 404


def test_denial_renders_403_and_404_through_the_real_serve_path() -> None:
    """A route whose handler calls gate.authorize() and is denied must return the policy's status
    (403/404), not a generic 500 — the gap unit-only tests missed."""
    from litestar.testing import TestClient

    from arvel.http import HttpKernel
    from arvel.kernel.application import Application
    from arvel.routing import Router

    async def forbidden(request: Any) -> dict[str, int]:
        await _gate().authorize("update", Post(), user=User(1))  # → 403 + custom message
        return {"ok": 1}

    async def hidden(request: Any) -> dict[str, int]:
        await _gate().authorize("view", Post(), user=User(1))  # deny_as_not_found → 404
        return {"ok": 1}

    app = Application.configure().create()
    router = Router()
    router.get("/forbidden", forbidden)
    router.get("/hidden", hidden)
    kernel = HttpKernel(app=app)
    router.apply_to(kernel)
    with TestClient(kernel.build()) as client:
        r = client.get("/forbidden")
        assert r.status_code == 403  # the fix: was a generic 500 before
        assert r.json()["message"] == "You don't own this post."  # custom deny message survives
        assert client.get("/hidden").status_code == 404  # deny_as_not_found
