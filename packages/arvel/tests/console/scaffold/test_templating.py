"""+ : literal string templating + no-unsubstituted-tokens sweep."""

from __future__ import annotations

import pytest
from arvel.console._scaffold import (
    TOKEN_KEYS,
    UnknownTemplateToken,
    find_unsubstituted_tokens,
    substitute,
)

TOKENS = {
    "project_name": "my-app",
    "project_name_pascal": "MyApp",
    "python_version": "3.14",
}


def test_token_keys_match_documented_set() -> None:
    """TOKEN_KEYS lists every supported token name ."""
    assert set(TOKEN_KEYS) == {"project_name", "project_name_pascal", "python_version"}


def test_substitute_replaces_each_token() -> None:
    content = (
        '[project]\nname = "{{ project_name }}"\n'
        'requires-python = ">={{ python_version }}"\n'
        "# Class name: {{ project_name_pascal }}\n"
    )
    result = substitute(content, TOKENS)
    assert result == (
        '[project]\nname = "my-app"\nrequires-python = ">=3.14"\n# Class name: MyApp\n'
    )


def test_substitute_handles_repeated_tokens() -> None:
    content = "{{ project_name }} and {{ project_name }} again"
    result = substitute(content, TOKENS)
    assert result == "my-app and my-app again"


def test_substitute_does_not_touch_unrelated_text() -> None:
    content = "no tokens at all here"
    assert substitute(content, TOKENS) == content


def test_substitute_unknown_token_in_content_raises() -> None:
    """A token in content but not in TOKEN_KEYS → ``UnknownTemplateToken``."""
    content = "Hello {{ stray_token }}"
    with pytest.raises(UnknownTemplateToken, match="stray_token"):
        substitute(content, TOKENS)


def test_substitute_unknown_key_in_tokens_dict_raises() -> None:
    """A key in the tokens dict outside TOKEN_KEYS → ValueError."""
    bad_tokens = {**TOKENS, "extra_key": "should-not-be-allowed"}
    with pytest.raises(ValueError, match="extra_key"):
        substitute("content", bad_tokens)


def test_find_unsubstituted_tokens_returns_matches() -> None:
    content = "{{ project_name }} is OK, {{ stray }} is not, and {{ also_stray }} either"
    found = find_unsubstituted_tokens(content)
    # All three are syntactically valid {{ ... }} patterns.
    assert "{{ project_name }}" in found
    assert "{{ stray }}" in found
    assert "{{ also_stray }}" in found


def test_find_unsubstituted_tokens_empty_when_none_present() -> None:
    assert find_unsubstituted_tokens("clean text, no tokens") == []


def test_unknown_template_token_is_value_error_subclass() -> None:
    assert issubclass(UnknownTemplateToken, ValueError)


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("{{ project_name }}", "my-app"),
        ("{{project_name}}", "my-app"),  # No spaces.
        ("{{ project_name}}", "my-app"),  # Trailing space only.
        ("{{project_name }}", "my-app"),  # Leading space only.
    ],
)
def test_substitute_tolerates_inner_whitespace(input_text: str, expected: str) -> None:
    """Token forms with varying inner whitespace all resolve correctly."""
    assert substitute(input_text, TOKENS) == expected
