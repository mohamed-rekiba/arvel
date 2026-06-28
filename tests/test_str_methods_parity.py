"""Str-helper parity (Laravel): common methods that were absent — case (lower/upper/ucfirst/lcfirst),
length/slicing (substr/take/char_at/reverse/repeat/words), whitespace+padding (squish/pad_*),
prefix/suffix (start/finish/chop_*/wrap), search (between/contains_all/position), replace
(replace_first/replace_last/replace_array/remove/swap), and predicates (is_ulid/is_json/is_url/uuid)."""

from __future__ import annotations

from arvel.support import Str


def test_case_helpers() -> None:
    assert Str.lower("ABc") == "abc"
    assert Str.upper("aBc") == "ABC"
    assert Str.ucfirst("hello") == "Hello"
    assert Str.lcfirst("Hello") == "hello"


def test_length_and_slicing() -> None:
    assert Str.length("abc") == 3
    assert Str.substr("hello", 1, 3) == "ell"
    assert Str.substr("hello", 2) == "llo"
    assert Str.take("hello", 2) == "he"
    assert Str.take("hello", -2) == "lo"
    assert Str.char_at("abc", 1) == "b"
    assert Str.char_at("abc", 9) is None
    assert Str.reverse("abc") == "cba"
    assert Str.repeat("ab", 3) == "ababab"
    assert Str.word_count("a b c") == 3
    assert Str.words("a b c d", 2) == "a b..."


def test_whitespace_and_padding() -> None:
    assert Str.squish("  a   b  c ") == "a b c"
    assert Str.pad_left("5", 3, "0") == "005"
    assert Str.pad_right("5", 3, "0") == "500"
    assert Str.pad_both("5", 3, "0") == "050"


def test_prefix_suffix() -> None:
    assert Str.start("path", "/") == "/path"
    assert Str.start("/path", "/") == "/path"  # idempotent
    assert Str.finish("path", "/") == "path/"
    assert Str.finish("path/", "/") == "path/"
    assert Str.chop_start("/api/x", "/api") == "/x"
    assert Str.chop_end("file.txt", ".txt") == "file"
    assert Str.wrap("x", "[", "]") == "[x]"
    assert Str.wrap("x", "'") == "'x'"


def test_search_and_extract() -> None:
    assert Str.between("[abc]", "[", "]") == "abc"
    # before-LAST end (Laravel beforeLast(after(...))) — nested/repeated end chars
    assert Str.between("a[x]b]c", "[", "]") == "x]b"
    assert Str.contains_all("hello world", ["hello", "world"]) is True
    assert Str.contains_all("hi", ["hi", "yo"]) is False
    assert Str.position("hello", "l") == 2
    assert Str.position("hello", "z") is None


def test_replace_helpers() -> None:
    assert Str.replace_first("a", "X", "banana") == "bXnana"
    assert Str.replace_last("a", "X", "banana") == "bananX"
    assert Str.replace_array("?", ["1", "2"], "? and ?") == "1 and 2"
    assert Str.remove("-", "a-b-c") == "abc"
    assert Str.swap({"a": "1", "b": "2"}, "ab") == "12"
    # single-pass (strtr semantics): substituted text is not re-processed
    assert Str.swap({"a": "b", "b": "a"}, "ab") == "ba"
    # longer keys win on overlap
    assert Str.swap({"foo": "X", "foobar": "Y"}, "foobar") == "Y"


def test_predicates_and_generators() -> None:
    assert Str.is_ulid(Str.ulid()) is True
    assert Str.is_ulid("nope") is False
    assert Str.is_json('{"a": 1}') is True
    assert Str.is_json("{bad") is False
    assert Str.is_url("https://x.com") is True
    assert Str.is_url("x.com") is False
    assert Str.is_uuid(Str.uuid()) is True  # generated UUID is valid
