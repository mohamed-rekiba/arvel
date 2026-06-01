"""Pure-logic mixins: trashed-mode parsing, publish timestamps, JSONB i18n."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from arvel.database.mixins import (
    PublishableMixin,
    TranslatableMixin,
    parse_trashed_mode,
)


class _QueryParams:
    def __init__(self, value: str | None) -> None:
        self._value = value

    def get(self, key: str, default: str) -> str:
        return self._value if self._value is not None else default


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("with", "with"), ("only", "only"), ("without", "without"), ("garbage", "without")],
)
def test_parse_trashed_mode_from_string(raw: str, expected: str) -> None:
    assert parse_trashed_mode(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("with", "with"), ("only", "only"), (None, "without")],
)
def test_parse_trashed_mode_from_request(raw: str | None, expected: str) -> None:
    request = SimpleNamespace(query_params=_QueryParams(raw))
    assert parse_trashed_mode(request) == expected


def test_resolve_published_at_clears_when_not_published() -> None:
    assert PublishableMixin.resolve_published_at("draft", datetime.now(UTC)) is None


def test_resolve_published_at_uses_explicit_timestamp() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    assert PublishableMixin.resolve_published_at("published", ts) == ts


def test_resolve_published_at_defaults_to_now() -> None:
    result = PublishableMixin.resolve_published_at("published", None)
    assert result is not None
    assert result.tzinfo is UTC


class _Doc(TranslatableMixin):
    def __init__(self, name: dict[str, Any] | None) -> None:
        self.name = name


def test_get_translation_returns_requested_locale() -> None:
    assert _Doc({"en": "Chair", "ar": "كرسي"}).get_translation("name", "ar") == "كرسي"


def test_get_translation_falls_back_to_en() -> None:
    assert _Doc({"en": "Chair"}).get_translation("name", "fr") == "Chair"


def test_get_translation_handles_missing_field() -> None:
    assert _Doc(None).get_translation("name", "ar") == ""


def test_set_translation_patches_single_locale() -> None:
    doc = _Doc({"en": "Chair"})
    doc.set_translation("name", "fr", "Chaise")
    assert doc.name == {"en": "Chair", "fr": "Chaise"}


def test_set_translation_from_empty_field() -> None:
    doc = _Doc(None)
    doc.set_translation("name", "en", "Table")
    assert doc.name == {"en": "Table"}


def test_translate_dict_resolves_locale_with_en_fallback() -> None:
    data = {"en": "Chair", "ar": "كرسي"}
    assert TranslatableMixin.translate_dict(data, "ar") == "كرسي"
    assert TranslatableMixin.translate_dict(data, "de") == "Chair"
    assert TranslatableMixin.translate_dict({}, "de") == ""
