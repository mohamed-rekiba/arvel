"""arvel.testing — the framework's own test-double assertions (FakeMailer/FakeQueue/FakeEvents/
FakeNotifications) and the TestResponse/ConsoleResult fluent assertion surface, including the
failure branches that raise ``AssertionError``."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.testing import (
    ConsoleResult,
    FakeEvents,
    FakeMailer,
    FakeNotifications,
    FakeQueue,
)
from arvel.testing import TestResponse as _TestResponse


class _MailA: ...


class _MailB: ...


async def test_fake_mailer_assertions() -> None:
    mailer = FakeMailer()
    mailer.assert_nothing_sent()
    await mailer.to("a@x.com").cc("c@x.com").bcc("b@x.com").send(_MailA())
    mailer.assert_sent(_MailA)
    with pytest.raises(AssertionError):
        mailer.assert_sent(_MailB)
    with pytest.raises(AssertionError):
        mailer.assert_nothing_sent()


async def test_fake_mailer_records_cc_bcc_and_assert_sent_predicate() -> None:
    mailer = FakeMailer()
    await mailer.to("a@x.com").cc("c@x.com").bcc("b@x.com").send(_MailA())
    assert mailer.recipients == [{"to": ["a@x.com"], "cc": ["c@x.com"], "bcc": ["b@x.com"]}]

    mailer.assert_sent(_MailA, lambda _m, r: "c@x.com" in r["cc"])
    mailer.assert_sent(_MailA, count=1)
    with pytest.raises(AssertionError):
        mailer.assert_sent(_MailA, lambda _m, r: "nope@x.com" in r["cc"])
    with pytest.raises(AssertionError):
        mailer.assert_sent(_MailA, count=2)


class _JobA: ...


class _JobB: ...


async def test_fake_queue_push_and_dispatch_assertions() -> None:
    queue = FakeQueue()
    queue.assert_nothing_pushed()
    queue.assert_not_dispatched(_JobA)
    await queue.push(_JobA, (1,), {"k": "v"})
    queue.assert_pushed(_JobA)
    queue.assert_dispatched(_JobA)
    with pytest.raises(AssertionError):
        queue.assert_pushed(_JobB)
    with pytest.raises(AssertionError):
        queue.assert_nothing_pushed()
    with pytest.raises(AssertionError):
        queue.assert_not_dispatched(_JobA)


async def test_fake_queue_assert_pushed_with_fn_count_and_queue() -> None:
    queue = FakeQueue()
    await queue.push(_JobA, (1,), {"k": "v"}, queue="high")
    await queue.push(_JobA, (2,), {"k": "w"}, queue="low")

    queue.assert_pushed(_JobA, lambda n, k: n == 1, queue="high")
    queue.assert_pushed(_JobA, count=2)
    with pytest.raises(AssertionError):
        queue.assert_pushed(_JobA, lambda n, k: n == 1, queue="low")  # wrong queue
    with pytest.raises(AssertionError):
        queue.assert_pushed(_JobA, count=1)  # actually 2


def test_fake_queue_push_signature_pinned_against_the_real_push() -> None:
    """A signature-drift contract test: FakeQueue.push must keep the same parameter names/kinds
    as QueueManager.push, so a future real-push signature change can't silently drift the fake out
    of sync (defaults are allowed to differ — the fake's are convenience-only)."""
    import inspect

    from arvel.queue import QueueManager

    fake_params = list(inspect.signature(FakeQueue.push).parameters.values())[1:]  # drop self
    real_params = list(inspect.signature(QueueManager.push).parameters.values())[1:]

    fake_shape = [(p.name, p.kind) for p in fake_params]
    real_shape = [(p.name, p.kind) for p in real_params]
    assert fake_shape == real_shape


class _EventA: ...


class _EventB: ...


async def test_fake_events_dispatch_until_and_assert() -> None:
    events = FakeEvents()
    events.listen(_EventA, lambda e: None)  # accepted + ignored
    assert await events.dispatch(_EventA()) == []
    assert await events.until(_EventB()) is None
    events.assert_dispatched(_EventA)
    with pytest.raises(AssertionError):
        events.assert_dispatched(type("Missing", (), {}))


async def test_fake_events_not_dispatched_and_nothing_dispatched() -> None:
    events = FakeEvents()
    events.assert_not_dispatched(_EventA)
    events.assert_nothing_dispatched()
    await events.dispatch(_EventA())
    with pytest.raises(AssertionError):
        events.assert_not_dispatched(_EventA)
    with pytest.raises(AssertionError):
        events.assert_nothing_dispatched()


class _Notification:
    def __init__(self, tag: str = "x") -> None:
        self.tag = tag

    def via(self, notifiable: Any) -> list[str]:
        return ["mail"]


async def test_fake_notifications_assertions() -> None:
    notes = FakeNotifications()
    notes.assert_nothing_sent()
    notes.assert_count(0)
    user = object()
    await notes.send_now(user, _Notification("hi"))
    notes.assert_sent_to(user, _Notification, callback=lambda n: n.tag == "hi")
    notes.assert_count(1)
    with pytest.raises(AssertionError):
        notes.assert_sent_to(user, _Notification, callback=lambda n: n.tag == "no")
    with pytest.raises(AssertionError):
        notes.assert_not_sent_to(user, _Notification)
    with pytest.raises(AssertionError):
        notes.assert_nothing_sent()
    with pytest.raises(AssertionError):
        notes.assert_count(5)


# --- TestResponse ---------------------------------------------------------
class _Raw:
    def __init__(
        self,
        status_code: int = 200,
        body: Any = None,
        headers: dict[str, str] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = text
        self.custom_attr = "escape-hatch"

    def json(self) -> Any:
        return self._body


def test_test_response_status_shortcuts() -> None:
    _TestResponse(_Raw(201)).assert_created()
    _TestResponse(_Raw(204)).assert_no_content()
    _TestResponse(_Raw(404)).assert_not_found()
    _TestResponse(_Raw(403)).assert_forbidden()
    _TestResponse(_Raw(401)).assert_unauthorized()
    _TestResponse(_Raw(422)).assert_unprocessable()
    _TestResponse(_Raw(200)).assert_ok()
    with pytest.raises(AssertionError):
        _TestResponse(_Raw(200)).assert_status(500)


def test_test_response_redirect() -> None:
    r = _TestResponse(_Raw(302, headers={"location": "/home"}))
    r.assert_redirect().assert_redirect("/home")
    with pytest.raises(AssertionError):
        r.assert_redirect("/elsewhere")
    with pytest.raises(AssertionError):
        _TestResponse(_Raw(200)).assert_redirect()


def test_test_response_json_helpers() -> None:
    raw = _Raw(200, body={"user": {"name": "ann"}, "items": [1, 2, 3]})
    r = _TestResponse(raw)
    r.assert_json({"user.name": "ann"})
    r.assert_json_path("user.name", "ann")
    r.assert_json_count(3, "items")
    r.assert_json_missing({"user.email": None})
    with pytest.raises(AssertionError):
        r.assert_json({"user.name": "bob"})
    with pytest.raises(AssertionError):
        r.assert_json_path("user.name", "bob")
    with pytest.raises(AssertionError):
        r.assert_json_count(1, "items")
    with pytest.raises(AssertionError):
        r.assert_json_count(1, "missing")  # absent path
    with pytest.raises(AssertionError):
        r.assert_json_count(1, "user")  # not an array
    with pytest.raises(AssertionError):
        r.assert_json_missing({"user.name": None})  # present


def test_test_response_see_header_and_escape_hatch() -> None:
    raw = _Raw(200, headers={"x-token": "abc"}, text="hello world")
    r = _TestResponse(raw)
    r.assert_see("hello")
    r.assert_header("x-token").assert_header("x-token", "abc")
    assert r.custom_attr == "escape-hatch"  # __getattr__ forwards to raw
    with pytest.raises(AssertionError):
        r.assert_see("goodbye")
    with pytest.raises(AssertionError):
        r.assert_header("missing")
    with pytest.raises(AssertionError):
        r.assert_header("x-token", "wrong")


def test_console_result_assertions() -> None:
    result = ConsoleResult(0, "all good\n")
    result.assert_exit_code(0).assert_output_contains("all good")
    with pytest.raises(AssertionError):
        result.assert_exit_code(1)
    with pytest.raises(AssertionError):
        result.assert_output_contains("nope")
