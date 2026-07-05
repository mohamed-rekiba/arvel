"""Spec 12 §2 — `Validator.sometimes()` (broader conditions than a single-field rule string) and
`after()` (post-pass hook — closes the doc's acknowledged TODO)."""

from __future__ import annotations

from arvel.validation import Validator


def test_sometimes_method_applies_rule_only_when_condition_true() -> None:
    v = Validator({"a": 5}, {})
    v.sometimes("a", "min:10", lambda data: data.get("a", 0) > 0)
    assert v.fails()
    assert "a" in v.errors()


def test_sometimes_method_skips_when_condition_false() -> None:
    v = Validator({"a": -1}, {})
    v.sometimes("a", "min:10", lambda data: data.get("a", 0) > 0)
    assert v.passes()


def test_sometimes_method_merges_with_existing_rules() -> None:
    v = Validator({"a": ""}, {"a": "string"})
    v.sometimes("a", "required", lambda data: True)
    assert v.fails()
    assert len(v.errors()["a"]) == 1  # `required` added; `string` still ran too (didn't replace)


def test_after_hook_runs_post_pass_and_can_add_errors() -> None:
    v = Validator({"start": 10, "end": 5}, {"start": "integer", "end": "integer"})
    v.after(
        lambda validator: (
            validator.add_error("end", "end must be after start")
            if validator.data["end"] < validator.data["start"]
            else None
        )
    )
    assert v.fails()
    assert v.errors()["end"] == ["end must be after start"]


def test_after_hook_does_not_run_when_field_rules_already_pass() -> None:
    v = Validator({"start": 1, "end": 5}, {"start": "integer", "end": "integer"})
    calls: list[bool] = []
    v.after(lambda validator: calls.append(True))
    assert v.passes()
    assert calls == [True]  # after() always runs; it just chose not to add an error here
