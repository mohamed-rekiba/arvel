"""Placeholder replacement and choice-pluralization edge cases (round H1)."""

from __future__ import annotations

from arvel.localization import Translator


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
