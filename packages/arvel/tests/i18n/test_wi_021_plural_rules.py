"""WI-arvel-021: positional pluralisation follows the locale plural rule.

Laravel's `MessageSelector::getPluralIndex` — not a raw count index — decides
which positional variant a count selects. The headline regression: a plain
two-form spec returns the singular only at count == 1.
"""

from __future__ import annotations

import pytest
from arvel.i18n.loader import TranslationValue
from arvel.i18n.pluralisation import select_plural_variant
from arvel.i18n.translator import Translator


class _MemoryLoader:
    """In-memory loader (duck-types TranslationLoader) so no files are needed."""

    def __init__(self, data: dict[str, dict[str, TranslationValue]]) -> None:
        self._data = data

    def load(self, locale: str, namespace: str) -> dict[str, TranslationValue]:
        return self._data.get(f"{locale}.{namespace}", {})


class TestEnglishTwoForm:
    """The common case: 'apple|apples'."""

    @pytest.mark.parametrize(
        ("count", "expected"),
        [(0, "apples"), (1, "apple"), (2, "apples"), (10, "apples")],
    )
    def test_singular_only_at_one(self, count: int, expected: str) -> None:
        out = select_plural_variant("apple|apples", count=count, replace={})
        assert out == expected


class TestFrenchZeroOrOne:
    """French treats 0 and 1 as singular."""

    @pytest.mark.parametrize(
        ("count", "expected"),
        [(0, "pomme"), (1, "pomme"), (2, "pommes")],
    )
    def test_zero_and_one_singular(self, count: int, expected: str) -> None:
        out = select_plural_variant("pomme|pommes", count=count, replace={}, locale="fr")
        assert out == expected


class TestRussianThreeForm:
    """Slavic rule selects one of three forms."""

    @pytest.mark.parametrize(
        ("count", "idx"),
        [(1, 0), (21, 0), (2, 1), (3, 1), (24, 1), (5, 2), (11, 2), (0, 2)],
    )
    def test_slavic_indices(self, count: int, idx: int) -> None:
        out = select_plural_variant("one|few|many", count=count, replace={}, locale="ru")
        assert out == ("one", "few", "many")[idx]


class TestArabicSixForm:
    """Arabic has six forms."""

    @pytest.mark.parametrize(
        ("count", "idx"),
        [(0, 0), (1, 1), (2, 2), (3, 3), (11, 4), (100, 5)],
    )
    def test_arabic_indices(self, count: int, idx: int) -> None:
        spec = "zero|one|two|few|many|other"
        out = select_plural_variant(spec, count=count, replace={}, locale="ar")
        assert out == spec.split("|")[idx]


class TestLocaleSubtagStripping:
    """A region tag like pt_BR resolves on its language subtag."""

    def test_pt_br_uses_portuguese_rule(self) -> None:
        # pt -> two-form (count == 1 singular).
        assert select_plural_variant("maçã|maçãs", count=2, replace={}, locale="pt_BR") == "maçãs"
        assert select_plural_variant("maçã|maçãs", count=1, replace={}, locale="pt-BR") == "maçã"

    def test_unknown_locale_falls_back_to_first_form(self) -> None:
        assert select_plural_variant("a|b", count=5, replace={}, locale="xx") == "a"


class TestTranslatorThreadsLocale:
    """Translator.choice passes its active locale into the plural rule."""

    def test_choice_uses_translator_locale(self) -> None:
        loader = _MemoryLoader(
            {
                "en.messages": {"apples": "apple|apples"},
                "fr.messages": {"apples": "pomme|pommes"},
            }
        )
        translator = Translator(loader, default_locale="en")

        assert translator.choice("messages.apples", count=1) == "apple"
        assert translator.choice("messages.apples", count=0) == "apples"

        translator.set_locale("fr")
        # French: 0 is singular.
        assert translator.choice("messages.apples", count=0) == "pomme"

    def test_per_call_locale_override(self) -> None:
        loader = _MemoryLoader({"fr.messages": {"apples": "pomme|pommes"}})
        translator = Translator(loader, default_locale="en")
        assert translator.choice("messages.apples", count=0, locale="fr") == "pomme"


class TestBracketSyntaxUnaffected:
    """Explicit bracket conditions still win regardless of locale rule."""

    @pytest.mark.parametrize(
        ("count", "expected"),
        [(0, "none"), (1, "few"), (4, "few"), (5, "other")],
    )
    def test_brackets_take_precedence(self, count: int, expected: str) -> None:
        spec = "{0}none|[1,4]few|other"
        assert select_plural_variant(spec, count=count, replace={}) == expected
