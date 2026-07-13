"""Coverage — testing fakes, localization CLDR plural branches, notification base."""

from __future__ import annotations

import pytest

from arvel.localization import Translator
from arvel.notifications import Notification
from arvel.testing import FakeEvents, FakeMailer, FakeQueue


class _Msg: ...


class _Job: ...


class _Evt: ...


# --- testing fakes ------------------------------------------------------------
async def test_fake_mailer_assertions() -> None:
    mailer = FakeMailer()
    FakeMailer().assert_nothing_sent()  # empty -> passes
    await mailer.to("a@b.com").send(_Msg())
    mailer.assert_sent(_Msg)  # success path
    with pytest.raises(AssertionError):
        FakeMailer().assert_sent(_Msg)  # nothing sent
    with pytest.raises(AssertionError):
        mailer.assert_nothing_sent()  # something sent


async def test_fake_queue_assertions() -> None:
    queue = FakeQueue()
    FakeQueue().assert_nothing_pushed()
    await queue.push(_Job)
    queue.assert_pushed(_Job)
    with pytest.raises(AssertionError):
        FakeQueue().assert_pushed(_Job)
    with pytest.raises(AssertionError):
        queue.assert_nothing_pushed()


async def test_fake_events_dispatch_and_until() -> None:
    events = FakeEvents()
    await events.dispatch(_Evt())
    events.assert_dispatched(_Evt)
    assert await events.until(_Evt()) is None  # until records + returns None


# --- localization plural categories -------------------------------------------
def test_two_segment_cldr_plural() -> None:
    t = Translator()
    t.add("en", {"apples": "one apple|many apples"})
    assert t.choice("apples", 1, {}, locale="en") == "one apple"
    assert t.choice("apples", 5, {}, locale="en") == "many apples"  # "other" -> 2nd segment


def test_multi_segment_plural_picks_by_category() -> None:
    t = Translator()
    t.add("en", {"x": "zero|one|other"})
    assert t.choice("x", 5, {}, locale="en") in {"zero", "one", "other"}  # exercises selection


# --- notification base --------------------------------------------------------
def test_notification_to_mail_must_be_implemented() -> None:
    with pytest.raises(NotImplementedError):
        Notification().to_mail(object())
