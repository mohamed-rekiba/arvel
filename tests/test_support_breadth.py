"""C1b — Number (Babel), Stringable, Collection/Str breadth."""

from __future__ import annotations

from arvel.support import Collection, Number, Str, Stringable


def test_number_formatting() -> None:
    assert Number.currency(1234.5, "USD", "en").startswith("$1,234")
    assert Number.percentage(25) == "25%"
    assert Number.human(1500) == "1.5K"
    assert Number.human(2_000_000) == "2M"


def test_stringable_fluent_chain() -> None:
    result = Str.of("  Hello World  ".strip()).lower().replace(" ", "-")
    assert isinstance(result, Stringable)
    assert result.to_str() == "hello-world"
    assert str(Str.of("FooBar").snake()) == "foo_bar"
    assert Str.of("hello@example.com").after("@").to_str() == "example.com"
    assert Str.of("hello@example.com").before("@").to_str() == "hello"


def test_str_breadth() -> None:
    assert Str.headline("email_notification_sent") == "Email Notification Sent"
    assert Str.is_uuid("12345678-1234-1234-1234-123456789abc") is True
    assert Str.is_uuid("nope") is False
    assert Str.mask("secret", "*", 0, 3) == "***ret"
    assert isinstance(Str.of("x"), Stringable)


def test_collection_breadth() -> None:
    c = Collection([{"team": "a", "n": 1}, {"team": "b", "n": 2}, {"team": "a", "n": 3}])
    grouped = c.group_by("team")
    assert set(grouped) == {"a", "b"}
    assert len(grouped["a"]) == 2

    keyed = Collection([{"id": 1}, {"id": 2}]).key_by("id")
    assert set(keyed) == {1, 2}

    assert Collection([1, 2, 3, 4]).chunk(2).all() == [[1, 2], [3, 4]]
    assert Collection([1, [2, [3]]]).flatten().all() == [1, 2, 3]
    assert Collection([{"n": 3}, {"n": 1}]).sort_by("n").pluck("n").all() == [1, 3]
    assert Collection([1, 2]).map_with_keys(lambda x: (x, x * 10)) == {1: 10, 2: 20}
