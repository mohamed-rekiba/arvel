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


def test_pull_returns_and_removes() -> None:
    session: dict[str, Any] = {"k": "v"}
    bag = FlashBag(session)
    assert bag.pull("k") == "v"
    assert "k" not in session
    assert bag.pull("k") is None  # already gone


def test_pull_default_for_missing_key() -> None:
    assert FlashBag({}).pull("nope", "fallback") == "fallback"


def test_increment_on_an_absent_key_starts_at_the_step() -> None:
    bag = FlashBag({})
    assert bag.increment("views") == 1
    assert bag.increment("views") == 2


def test_increment_custom_step() -> None:
    bag = FlashBag({})
    assert bag.increment("hits", step=5) == 5
    assert bag.increment("hits", step=5) == 10


def test_decrement_subtracts_the_step() -> None:
    session: dict[str, Any] = {"credits": 10}
    bag = FlashBag(session)
    assert bag.decrement("credits") == 9
    assert bag.decrement("credits", step=4) == 5


def test_flash_only_flashes_the_named_subset_for_old() -> None:
    session: dict[str, Any] = {}
    bag = FlashBag(session)
    bag.flash_only({"name": "ada", "password": "secret", "email": "a@b.com"}, ["name", "email"])
    assert bag.old() == {"name": "ada", "email": "a@b.com"}


def test_flash_only_accepts_a_single_key() -> None:
    session: dict[str, Any] = {}
    bag = FlashBag(session)
    bag.flash_only({"name": "ada", "password": "secret"}, "name")
    assert bag.old() == {"name": "ada"}
