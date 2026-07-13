"""arvel.validation — assorted rule-engine branches: FormRequest default hooks, the
sometimes/nullable skips, wildcard-on-non-list, stop-on-first-failure, and the json rule's
non-string guard."""

from __future__ import annotations

from arvel.validation import FormRequest, Validator


def test_form_request_default_hooks() -> None:
    assert FormRequest.messages() == {}
    assert FormRequest.attributes() == {}


def test_sometimes_absent_field_is_skipped() -> None:
    assert Validator({}, {"x": "sometimes|integer"}).passes()


def test_nullable_none_is_skipped() -> None:
    assert Validator({"x": None}, {"x": "nullable|integer"}).passes()


def test_wildcard_on_non_list_short_circuits() -> None:
    assert Validator({"tags": "not-a-list"}, {"tags.*": "string"}).passes()


def test_stop_on_first_failure_reports_one_field() -> None:
    v = Validator(
        {"a": "", "b": ""},
        {"a": "required", "b": "required"},
        stop_on_first_failure=True,
    )
    assert v.fails()
    assert len(v.errors()) == 1


def test_json_rule_rejects_non_string() -> None:
    assert Validator({"x": 123}, {"x": "json"}).fails()
    assert Validator({"x": '{"ok": true}'}, {"x": "json"}).passes()
