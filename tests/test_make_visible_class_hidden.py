"""ch 07 — make_visible() must reveal a class-__hidden__ attribute (Laravel makeVisible),
not only un-hide one previously hidden via make_hidden()."""

from __future__ import annotations

from arvel.database import Model


class _User(Model):
    __fields__ = {"name": str, "password": str}
    __hidden__ = ["password"]


def test_class_hidden_is_excluded_by_default() -> None:
    u = _User(name="Ada", password="secret")
    assert "password" not in u.to_dict()


def test_make_visible_reveals_class_hidden() -> None:
    u = _User(name="Ada", password="secret")
    u.make_visible("password")
    assert u.to_dict()["password"] == "secret"


def test_make_hidden_then_make_visible_round_trips() -> None:
    u = _User(name="Ada", password="secret")
    u.make_hidden("name")
    assert "name" not in u.to_dict()
    u.make_visible("name")
    assert "name" in u.to_dict()


def test_make_hidden_still_hides_extra() -> None:
    u = _User(name="Ada", password="secret")
    u.make_hidden("name")
    assert "name" not in u.to_dict()
