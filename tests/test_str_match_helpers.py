"""Str — after_last / before_last / is_ (Laravel Str::afterLast/beforeLast/is parity). after_last/
before_last split on the LAST occurrence (return the whole string when absent); is_ matches a pattern
where only ``*`` is a wildcard (every other char is literal)."""

from __future__ import annotations

from arvel.support import Str


def test_after_last() -> None:
    assert Str.after_last("a.b.c", ".") == "c"
    assert Str.after_last("App/Models/User", "/") == "User"
    assert Str.after_last("nodot", ".") == "nodot"  # absent → whole string
    assert Str.after_last("abc", "") == "abc"  # empty search → whole string (no ValueError)


def test_before_last() -> None:
    assert Str.before_last("a.b.c", ".") == "a.b"
    assert Str.before_last("App/Models/User", "/") == "App/Models"
    assert Str.before_last("nodot", ".") == "nodot"  # absent → whole string
    assert Str.before_last("abc", "") == "abc"


def test_is_wildcard_match() -> None:
    assert Str.is_("foo*", "foobar") is True
    assert Str.is_("*", "anything") is True
    assert Str.is_("foo/*", "foo/bar/baz") is True  # * spans slashes
    assert Str.is_("foo", "foo") is True  # exact
    assert Str.is_("foo", "bar") is False
    assert Str.is_("foo*", "barfoo") is False


def test_is_treats_only_star_as_wildcard() -> None:
    # the dot is literal, not a regex metachar
    assert Str.is_("foo.bar", "foo.bar") is True
    assert Str.is_("foo.bar", "fooXbar") is False
