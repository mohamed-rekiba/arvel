"""Placeholder replacement and choice-pluralization edge cases (round H1)."""

from __future__ import annotations

import pytest

from arvel.localization import TranslationMissingError, Translator


def _t(line: str) -> Translator:
    return Translator({"en": {"k": line}})


def test_longer_placeholder_is_not_clobbered_by_a_prefix_key() -> None:
    # :name must not eat the :name_full token when both are supplied
    t = _t(":name / :name_full")
    assert t.get("k", {"name": "Bob", "name_full": "Bob Smith"}) == "Bob / Bob Smith"


def test_case_variant_placeholders() -> None:
    t = _t(":name greets :NAME as :Name")
    assert t.get("k", {"name": "bob"}) == "bob greets BOB as Bob"


def test_brace_form_still_replaced() -> None:
    assert _t("hi {name}").get("k", {"name": "Bob"}) == "hi Bob"


def test_choice_exact_count_selector() -> None:
    t = _t("{0} none|{1} one|[2,*] many")
    assert t.choice("k", 0) == "none"
    assert t.choice("k", 1) == "one"
    assert t.choice("k", 5) == "many"


def test_choice_bounded_interval_selector() -> None:
    t = _t("[0,0] empty|[1,19] some|[20,*] lots")
    assert t.choice("k", 0) == "empty"
    assert t.choice("k", 10) == "some"
    assert t.choice("k", 19) == "some"
    assert t.choice("k", 20) == "lots"


# --- has() / get_or_fail() ----------------------------------------------------
def test_has_is_true_for_a_present_key_and_false_for_a_miss() -> None:
    t = _t("hello")
    assert t.has("k") is True
    assert t.has("missing") is False


def test_has_checks_the_fallback_locale_too() -> None:
    t = Translator({"en": {"k": "hello"}}, fallback="en")
    assert t.has("k", locale="fr") is True  # absent in fr, present in the fallback
    assert t.has("nope", locale="fr") is False


def test_get_or_fail_returns_the_line_when_present() -> None:
    t = _t("hi :name")
    assert t.get_or_fail("k", {"name": "Bob"}) == "hi Bob"


def test_get_or_fail_raises_on_a_real_miss_unlike_get() -> None:
    t = _t("hello")
    assert t.get("missing") == "missing"  # get() silently falls back to the key itself
    with pytest.raises(TranslationMissingError, match="missing"):
        t.get_or_fail("missing")


def test_choice_low_star_and_star_high() -> None:
    assert _t("[*,5] low|[6,*] high").choice("k", 3) == "low"
    assert _t("[*,5] low|[6,*] high").choice("k", 6) == "high"


def test_choice_falls_back_to_positional_when_no_interval_matches() -> None:
    # no explicit selector matches n -> positional CLDR over the plain segments
    t = _t("apple|apples")
    assert t.choice("k", 1) == "apple"
    assert t.choice("k", 3) == "apples"


def test_choice_count_placeholder_available() -> None:
    assert _t("[1,*] :count items").choice("k", 4) == "4 items"
