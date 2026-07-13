"""Stringable fluent parity: Str::of(...) chaining was missing ~40 methods that Str (static)
gained in the helpers pass. Each transform returns a new Stringable so calls chain; terminals return
plain values; explode bridges to a Collection."""

from __future__ import annotations

from arvel.support import Collection, Str


def test_fluent_chaining() -> None:
    assert str(Str.of("  hello   world  ").trim().squish().title()) == "Hello World"
    assert str(Str.of("Hello World").slug().finish("/")) == "hello-world/"
    assert str(Str.of("hi").ucfirst().append("!")) == "Hi!"
    assert str(Str.of("ab").reverse().repeat(2)) == "baba"


def test_inflection_and_case() -> None:
    assert str(Str.of("foo_bar").studly()) == "FooBar"
    assert str(Str.of("box").plural()) == "boxes"
    assert str(Str.of("boxes").singular()) == "box"
    assert str(Str.of("HELLO").lower()) == "hello"
    assert str(Str.of("hello").upper()) == "HELLO"


def test_slicing_and_replace() -> None:
    assert str(Str.of("hello").substr(1, 3)) == "ell"
    assert str(Str.of("hello").take(-2)) == "lo"
    assert str(Str.of("a[x]b]c").between("[", "]")) == "x]b"  # before-LAST, matches Str.between
    assert str(Str.of("banana").replace_first("a", "X")) == "bXnana"
    assert str(Str.of("ab").swap({"a": "b", "b": "a"})) == "ba"  # single-pass strtr
    assert str(Str.of("5").pad_left(3, "0")) == "005"
    assert str(Str.of("secret").mask("*", 1, 3)) == "s***et"
    assert str(Str.of("x").wrap("[", "]")) == "[x]"


def test_fluent_control_flow() -> None:
    assert str(Str.of("hi").when(True, lambda s: s.upper())) == "HI"
    assert str(Str.of("hi").when(False, lambda s: s.upper())) == "hi"
    assert str(Str.of("hi").unless(False, lambda s: s.upper())) == "HI"
    captured: list[str] = []
    assert str(Str.of("x").tap(lambda s: captured.append(str(s)))) == "x"
    assert captured == ["x"]
    assert Str.of("hello").pipe(lambda s: s.length()) == 5


def test_terminals() -> None:
    assert Str.of("abc").length() == 3
    assert Str.of("a b c").word_count() == 3
    assert Str.of("abc").char_at(1) == "b"
    assert Str.of("abc").char_at(9) is None
    assert Str.of("hello world").contains_all(["hello", "world"]) is True
    assert Str.of("hello").position("l") == 2
    assert Str.of("").is_empty() is True
    assert Str.of("x").is_not_empty() is True
    assert Str.of('{"a": 1}').is_json() is True
    assert Str.of("https://x.com").is_url() is True
    assert Str.of(Str.uuid()).is_uuid() is True
    assert Str.of(Str.ulid()).is_ulid() is True


def test_explode_bridges_to_collection() -> None:
    result = Str.of("a,b,c").explode(",")
    assert isinstance(result, Collection)
    assert result.map(lambda x: x.upper()).all() == ["A", "B", "C"]
