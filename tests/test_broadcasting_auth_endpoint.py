"""Broadcasting (spec 19 §1) — the ``/broadcasting/auth`` endpoint: a real HTTP round-trip through
Litestar (the actual served/consumer path), not just a handler-level unit call. Proves the
routing-layer wiring: the endpoint sees BOTH the authenticated user (auth) and the registered
channel callback (broadcasting) without either module importing the other."""

from __future__ import annotations

from typing import Any

from arvel import Application
from arvel.auth.middleware import Authenticate
from arvel.broadcasting import BroadcastManager
from arvel.http import HttpKernel
from arvel.http.middleware import AuthenticateMiddleware
from arvel.kernel import set_application
from arvel.routing.broadcasting_auth import broadcasting_auth
from arvel.testing import client


class FakeUser:
    def __init__(self, identifier: str) -> None:
        self.id = identifier


def _app_and_kernel(manager: BroadcastManager) -> HttpKernel:
    app = Application()
    app.make("config").set("app.key", "test-secret")
    app.instance("broadcast", manager)

    def resolver(request: Any) -> FakeUser | None:
        token = request.header("authorization")
        return FakeUser(token.removeprefix("Bearer ")) if token else None

    app.instance("user_resolver", resolver)
    set_application(app)

    kernel = HttpKernel(app)
    kernel.global_middleware = [AuthenticateMiddleware]
    kernel.add_route(["POST"], "/broadcasting/auth", broadcasting_auth, middleware=[Authenticate])
    return kernel


def test_authorized_user_gets_a_signature_for_a_private_channel() -> None:
    manager = BroadcastManager()
    manager.channel("chat.{id}", lambda user, chat_id: user.id == chat_id)
    kernel = _app_and_kernel(manager)
    try:
        with client(kernel.build()) as http:
            r = http.post(
                "/broadcasting/auth",
                headers={"authorization": "Bearer 5"},
                data={"channel_name": "private-chat.5", "socket_id": "s1"},
            )
        r.assert_ok()
        auth = r.raw.json()["auth"]
        assert isinstance(auth, str) and auth  # a real HMAC signature, not a bare bool
    finally:
        set_application(None)


def test_unauthorized_user_gets_403() -> None:
    manager = BroadcastManager()
    manager.channel("chat.{id}", lambda user, chat_id: user.id == chat_id)
    kernel = _app_and_kernel(manager)
    try:
        with client(kernel.build()) as http:
            r = http.post(
                "/broadcasting/auth",
                headers={"authorization": "Bearer 9"},
                data={"channel_name": "private-chat.5", "socket_id": "s1"},
            )
        r.assert_forbidden()
    finally:
        set_application(None)


def test_guest_is_rejected_before_reaching_the_channel_callback() -> None:
    manager = BroadcastManager()
    manager.channel("chat.{id}", lambda user, chat_id: True)  # would allow anyone
    kernel = _app_and_kernel(manager)
    try:
        with client(kernel.build()) as http:
            r = http.post(
                "/broadcasting/auth", data={"channel_name": "private-chat.5", "socket_id": "s1"}
            )
        r.assert_unauthorized()  # no bearer token -> guest -> 401, never reaches the callback
    finally:
        set_application(None)


def test_presence_channel_returns_member_data() -> None:
    manager = BroadcastManager()
    manager.channel("room.{id}", lambda user, room_id: {"id": user.id, "room": room_id})
    kernel = _app_and_kernel(manager)
    try:
        with client(kernel.build()) as http:
            r = http.post(
                "/broadcasting/auth",
                headers={"authorization": "Bearer ada"},
                data={"channel_name": "presence-room.9", "socket_id": "s1"},
            )
        r.assert_ok()
        assert r.raw.json()["channel_data"] == {"id": "ada", "room": "9"}
    finally:
        set_application(None)


def test_empty_app_key_refuses_to_sign() -> None:
    # review nit: an HMAC keyed with "" is forgeable — an authorized request must NOT get a weak
    # signature under a misconfigured (empty) app.key; the endpoint 500s instead
    manager = BroadcastManager()
    manager.channel("chat.{id}", lambda user, chat_id: user.id == chat_id)
    kernel = _app_and_kernel(manager)
    from arvel.kernel import app as current_app

    current_app().make("config").set("app.key", "")  # blank the key
    try:
        with client(kernel.build()) as http:
            r = http.post(
                "/broadcasting/auth",
                headers={"authorization": "Bearer 5"},
                data={"channel_name": "private-chat.5", "socket_id": "s1"},
            )
        assert r.status_code == 500  # would-be-authorized, but no weak signature handed out
    finally:
        set_application(None)
