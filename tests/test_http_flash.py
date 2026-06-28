"""HTTP/Views (doc 09) — session flash + error bag."""

from __future__ import annotations

from typing import Any

from arvel.http.flash import FlashBag


def test_flash_and_read() -> None:
    session: dict[str, Any] = {}
    bag = FlashBag(session)
    bag.flash("status", "Saved!")
    assert bag.get("status") == "Saved!"
    assert bag.has("status")
    assert bag.all() == {"status": "Saved!"}
    assert session["_flash"] == {"status": "Saved!"}  # persisted into the session


def test_default_for_missing_key() -> None:
    assert FlashBag({}).get("nope", "fallback") == "fallback"


def test_error_bag_roundtrip() -> None:
    session: dict[str, Any] = {}
    bag = FlashBag(session)
    bag.flash_errors({"email": ["The email is invalid."]})
    assert bag.errors() == {"email": ["The email is invalid."]}


def test_clear_empties_flash_and_errors() -> None:
    session: dict[str, Any] = {"_flash": {"a": 1}, "_errors": {"x": ["y"]}}
    bag = FlashBag(session)
    bag.clear()
    assert bag.all() == {}
    assert bag.errors() == {}
