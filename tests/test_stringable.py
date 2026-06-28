"""Coverage — the fluent Stringable wrapper (doc 01 support)."""

from __future__ import annotations

from arvel.support.stringable import Stringable


def test_case_and_chaining() -> None:
    assert str(Stringable("Hi").upper()) == "HI"
    assert str(Stringable("Hi").lower()) == "hi"
    assert str(Stringable("a").append("b", "c")) == "abc"
    assert str(Stringable("c").prepend("a", "b")) == "abc"
    assert str(Stringable("a-b").replace("-", "_")) == "a_b"


def test_after_before() -> None:
    assert str(Stringable("name@example.com").after("@")) == "example.com"
    assert str(Stringable("name@example.com").before("@")) == "name"
    assert str(Stringable("plain").after("@")) == "plain"  # missing → unchanged
    assert str(Stringable("plain").before("@")) == "plain"


def test_limit() -> None:
    assert str(Stringable("hello").limit(10)) == "hello"
    assert str(Stringable("hello world").limit(5)) == "hello..."
    assert str(Stringable("hello world").limit(5, end="…")) == "hello…"


def test_inflection_helpers() -> None:
    assert str(Stringable("hello world").title()) == "Hello World"
    assert str(Stringable("HelloWorld").snake()) == "hello_world"
    assert str(Stringable("hello_world").camel()) == "helloWorld"
    assert str(Stringable("hello_world").kebab()) == "hello-world"
    assert str(Stringable("Hello World!").slug()) == "hello-world"
    assert str(Stringable("a b").slug("_")) == "a_b"


def test_predicates() -> None:
    s = Stringable("hello world")
    assert s.contains("world")
    assert s.starts_with("hello")
    assert s.ends_with("world")
    assert not s.contains("xyz")


def test_dunders() -> None:
    assert Stringable("x") == "x"
    assert Stringable("x") == Stringable("x")
    assert Stringable("x") != Stringable("y")
    assert (Stringable("x") == 5) is False  # NotImplemented → False
    assert repr(Stringable("x")) == "Stringable('x')"
    assert Stringable("x").to_str() == "x"
    assert hash(Stringable("x")) == hash("x")
