"""Flash aging — flashed data (status messages + the error bag) survives **exactly one request**
(Laravel ``ageFlashData``). Regression for the latent bug where flashes persisted across every
subsequent request because nothing ever aged the bag.

``StartSession`` ages the bag at request *start* (when the session loads), so the aging is uniform
across the success path (handler flashes during the request) and the exception path (the error
renderer flashes *after* the session middleware's teardown)."""

from __future__ import annotations

from typing import Any

from arvel.http.flash import FlashBag
from arvel.http.middleware import StartSession


class FakeRequest:
    def __init__(self, sid: str) -> None:
        self._sid = sid
        self.session: dict[str, Any] | None = None

    def cookie(self, name: str, default: str | None = None) -> str | None:
        return self._sid if self._sid is not None else default


async def _request(store: dict[str, dict[str, Any]], sid: str, action: Any) -> dict[str, Any]:
    """Drive one request through StartSession against a persisted store; return what `action` saw."""
    seen: dict[str, Any] = {}

    async def destination(req: Any) -> str:
        action(FlashBag(req.session), seen)
        return "ok"

    await StartSession(store=store).handle(FakeRequest(sid), destination)
    return seen


async def test_status_flash_survives_exactly_one_request() -> None:
    store: dict[str, dict[str, Any]] = {}
    sid = "s1"
    await _request(store, sid, lambda bag, _: bag.flash("status", "Saved!"))
    b = await _request(store, sid, lambda bag, seen: seen.update(status=bag.get("status")))
    assert b["status"] == "Saved!"  # visible on the very next request
    c = await _request(store, sid, lambda bag, seen: seen.update(status=bag.get("status")))
    assert c["status"] is None  # ...and gone the request after (aged out)


async def test_error_bag_survives_exactly_one_request() -> None:
    store: dict[str, dict[str, Any]] = {}
    sid = "s2"
    await _request(store, sid, lambda bag, _: bag.flash_errors({"email": ["Bad."]}))
    b = await _request(store, sid, lambda bag, seen: seen.update(errors=bag.errors()))
    assert b["errors"] == {"email": ["Bad."]}  # next request sees them
    c = await _request(store, sid, lambda bag, seen: seen.update(errors=bag.errors()))
    assert c["errors"] == {}  # aged out after one request


async def test_reflashing_extends_one_more_request() -> None:
    store: dict[str, dict[str, Any]] = {}
    sid = "s3"
    await _request(store, sid, lambda bag, _: bag.flash("m", "x"))

    def read_and_reflash(bag: FlashBag, seen: dict[str, Any]) -> None:
        seen["m"] = bag.get("m")
        bag.flash("m", "x")  # re-flash → keep for another hop

    b = await _request(store, sid, read_and_reflash)
    assert b["m"] == "x"  # still there on B
    c = await _request(store, sid, lambda bag, seen: seen.update(m=bag.get("m")))
    assert c["m"] == "x"  # survived to C because B re-flashed it
    d = await _request(store, sid, lambda bag, seen: seen.update(m=bag.get("m")))
    assert d["m"] is None  # then aged out


def test_age_is_a_noop_on_an_empty_session() -> None:
    session: dict[str, Any] = {}
    FlashBag(session).age()  # must not raise / create spurious keys that break callers
    assert FlashBag(session).all() == {}
    assert FlashBag(session).errors() == {}


def test_reads_after_aging_leave_no_session_residue() -> None:
    """A read (get/has/all) must not re-create an empty ``_flash`` after the bag was aged empty —
    callers that snapshot the session (regeneration, exact-equality tests) must see only real data."""
    session: dict[str, Any] = {"_token": "abc"}
    bag = FlashBag(session)
    bag.flash("status", "hi")
    bag.age()  # status is fresh → kept; nothing dropped
    bag.age()  # now stale → dropped, bag emptied + removed
    assert bag.get("status") is None and bag.has("status") is False and bag.all() == {}
    assert session == {"_token": "abc"}  # no _flash / _flash_fresh residue from the reads
