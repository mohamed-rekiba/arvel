"""arvel.support.Str — Laravel-parity string facade (Epic 049 Stories 11-12)."""

from __future__ import annotations

import re
import string

import pytest
from arvel.support import Str


class TestStrSlug:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Hello World", "hello-world"),
            ("Hello   World", "hello-world"),
            ("hello-world", "hello-world"),
            ("HÉLLÔ WÖRLD", "hello-world"),
            ("AB!@#CD", "ab-cd"),
            ("  leading  ", "leading"),
            ("", ""),
        ],
    )
    def test_default_separator(self, raw: str, expected: str) -> None:
        assert Str.slug(raw) == expected

    def test_custom_separator(self) -> None:
        assert Str.slug("Hello World", separator="_") == "hello_world"

    def test_underscore_separator_treats_dashes_as_words(self) -> None:
        assert Str.slug("foo-bar baz", separator="_") == "foo_bar_baz"


class TestStrHeadline:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("hello_world_greeting", "Hello World Greeting"),
            ("helloWorldGreeting", "Hello World Greeting"),
            ("HelloWorldGreeting", "Hello World Greeting"),
            ("hello-world", "Hello World"),
            ("alreadyOne", "Already One"),
            ("", ""),
        ],
    )
    def test_headline(self, raw: str, expected: str) -> None:
        assert Str.headline(raw) == expected


class TestStrIsUuid:
    def test_returns_true_for_valid_uuid(self) -> None:
        assert Str.is_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_returns_true_for_uppercase_uuid(self) -> None:
        assert Str.is_uuid("550E8400-E29B-41D4-A716-446655440000") is True

    @pytest.mark.parametrize(
        "raw",
        [
            "not-a-uuid",
            "550e8400-e29b-41d4-a716",
            "",
            "550e8400e29b41d4a716446655440000",
            "550e8400-e29b-41d4-a716-44665544000z",
        ],
    )
    def test_returns_false_for_invalid(self, raw: str) -> None:
        assert Str.is_uuid(raw) is False


class TestStrWordCount:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("hello world", 2),
            ("  hello   world  ", 2),
            ("one", 1),
            ("", 0),
            ("a b c d e", 5),
        ],
    )
    def test_word_count(self, raw: str, expected: int) -> None:
        assert Str.word_count(raw) == expected


class TestStrLimit:
    def test_truncates_with_default_ellipsis(self) -> None:
        assert Str.limit("hello world", 5) == "hello..."

    def test_custom_end(self) -> None:
        assert Str.limit("hello world", 5, end="…") == "hello…"

    def test_no_truncation_when_shorter(self) -> None:
        assert Str.limit("hi", 5) == "hi"

    def test_exact_length_no_change(self) -> None:
        assert Str.limit("hello", 5) == "hello"


class TestStrPad:
    def test_pad_left(self) -> None:
        assert Str.pad_left("5", 3, "0") == "005"

    def test_pad_right(self) -> None:
        assert Str.pad_right("5", 3, "0") == "500"

    def test_pad_both(self) -> None:
        assert Str.pad_both("5", 5, "_") == "__5__"

    def test_pad_noop_when_long_enough(self) -> None:
        assert Str.pad_left("hello", 3, "_") == "hello"


class TestStrCaseConverters:
    def test_snake(self) -> None:
        assert Str.snake("UserProfile") == "user_profile"

    def test_camel(self) -> None:
        assert Str.camel("user_profile") == "userProfile"

    def test_kebab(self) -> None:
        assert Str.kebab("UserProfile") == "user-profile"

    def test_studly(self) -> None:
        assert Str.studly("user_profile") == "UserProfile"


class TestStrStartsEndsContains:
    def test_starts_with_string(self) -> None:
        assert Str.starts_with("hello world", "hello") is True
        assert Str.starts_with("hello world", "world") is False

    def test_starts_with_tuple(self) -> None:
        assert Str.starts_with("hello", ("hi", "hello")) is True
        assert Str.starts_with("hello", ("hi", "goodbye")) is False

    def test_ends_with_string(self) -> None:
        assert Str.ends_with("hello.json", ".json") is True
        assert Str.ends_with("hello.json", ".yaml") is False

    def test_ends_with_tuple(self) -> None:
        assert Str.ends_with("hello.json", (".yaml", ".json")) is True

    def test_contains_string(self) -> None:
        assert Str.contains("hello world", "lo wo") is True
        assert Str.contains("hello world", "absent") is False

    def test_contains_tuple_any(self) -> None:
        assert Str.contains("hello world", ("absent", "world")) is True
        assert Str.contains("hello world", ("absent", "missing")) is False


class TestStrRandom:
    def test_random_default_length(self) -> None:
        out = Str.random()
        assert len(out) == 16
        # default alphabet is letters+digits
        assert all(c.isalnum() for c in out)

    def test_random_custom_length(self) -> None:
        assert len(Str.random(40)) == 40

    def test_random_negative_or_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="length must be positive"):
            Str.random(0)


class TestStrPassword:
    def test_default_length(self) -> None:
        out = Str.password()
        assert len(out) == 32

    def test_letters_only(self) -> None:
        out = Str.password(20, letters=True, numbers=False, symbols=False, spaces=False)
        assert len(out) == 20
        assert all(c.isalpha() for c in out)

    def test_numbers_only(self) -> None:
        out = Str.password(10, letters=False, numbers=True, symbols=False, spaces=False)
        assert len(out) == 10
        assert all(c.isdigit() for c in out)

    def test_symbols_pool_present(self) -> None:
        out = Str.password(200, letters=False, numbers=False, symbols=True, spaces=False)
        assert all(c in string.punctuation for c in out)

    def test_spaces_pool_present(self) -> None:
        out = Str.password(200, letters=False, numbers=False, symbols=False, spaces=True)
        # 200 chars: probability that no space appears is effectively zero
        assert " " in out

    def test_empty_pool_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            Str.password(10, letters=False, numbers=False, symbols=False, spaces=False)

    def test_uniqueness(self) -> None:
        # 32 chars from the default ~94-char pool: collision is implausible
        a = Str.password()
        b = Str.password()
        assert a != b


class TestStrAfterBefore:
    def test_after(self) -> None:
        assert Str.after("hello@world.com", "@") == "world.com"
        # Not present: returns the full subject
        assert Str.after("hello", "@") == "hello"

    def test_before(self) -> None:
        assert Str.before("hello@world.com", "@") == "hello"
        # Not present: returns the full subject
        assert Str.before("hello", "@") == "hello"

    def test_after_last(self) -> None:
        assert Str.after_last("a.b.c", ".") == "c"

    def test_before_last(self) -> None:
        assert Str.before_last("a.b.c", ".") == "a.b"


class TestStrBetween:
    def test_between(self) -> None:
        assert Str.between("foo[bar]baz", "[", "]") == "bar"


class TestStrMatchesRegex:
    """Sanity: facade methods return primitives, not regex match objects."""

    def test_slug_returns_pure_ascii(self) -> None:
        out = Str.slug("Café déjà vu")
        assert re.match(r"^[a-z0-9-]+$", out)
