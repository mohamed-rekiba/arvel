"""Date validation rules — deferred from the validation-rules pass because they need a
format-code decision. arvel is Python, so date_format uses Python strftime codes (not the PHP
codes). date/before/after/date_equals parse via stdlib datetime (ISO + common formats); before/after
resolve their arg as another field if present, else a literal date string. All were silent no-ops."""

from __future__ import annotations

from arvel.validation import ValidationException, Validator


def _passes(data: dict, rules: dict) -> bool:
    try:
        Validator(data, rules).validate()
        return True
    except ValidationException:
        return False


def test_date_rule() -> None:
    assert _passes({"x": "2020-01-15"}, {"x": "date"})  # ISO
    assert _passes({"x": "2020-01-15T10:30:00"}, {"x": "date"})  # ISO datetime
    assert _passes({"x": "01/15/2020"}, {"x": "date"})  # common US
    assert not _passes({"x": "not-a-date"}, {"x": "date"})
    assert not _passes({"x": 123}, {"x": "date"})  # non-string
    assert _passes({"x": None}, {"x": "nullable|date"})  # nullable still skips


def test_date_format_rule() -> None:
    assert _passes({"x": "2020-01-15"}, {"x": "date_format:%Y-%m-%d"})
    assert not _passes({"x": "01/15/2020"}, {"x": "date_format:%Y-%m-%d"})  # wrong format
    assert not _passes({"x": "2020-13-99"}, {"x": "date_format:%Y-%m-%d"})  # impossible date


def test_before_after_literal() -> None:
    assert _passes({"x": "2019-01-01"}, {"x": "before:2020-01-01"})
    assert not _passes({"x": "2025-01-01"}, {"x": "before:2020-01-01"})
    assert _passes({"x": "2025-01-01"}, {"x": "after:2020-01-01"})
    assert not _passes({"x": "2019-01-01"}, {"x": "after:2020-01-01"})


def test_before_after_field_reference() -> None:
    # arg resolves to another field when present
    assert _passes({"start": "2020-01-01", "end": "2020-06-01"}, {"start": "before:end"})
    assert not _passes({"start": "2020-06-01", "end": "2020-01-01"}, {"start": "before:end"})
    assert _passes({"start": "2020-01-01", "end": "2020-06-01"}, {"end": "after:start"})


def test_date_equals_rule() -> None:
    assert _passes({"x": "2020-01-01"}, {"x": "date_equals:2020-01-01"})
    assert not _passes({"x": "2020-01-02"}, {"x": "date_equals:2020-01-01"})


def test_date_rule_message() -> None:
    import pytest

    with pytest.raises(ValidationException) as exc:
        Validator({"published_at": "nope"}, {"published_at": "date"}).validate()
    assert "not a valid date" in str(exc.value)
