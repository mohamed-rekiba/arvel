"""Spec 12 §2 — presence/conditional rules, `exclude*`, and `bail`/`stop_on_first_failure`.

Table-driven: every rule gets a passing case and a failing case; conditional rules react to a
sibling field (incl. dot-nested)."""

from __future__ import annotations

from arvel.validation import Validator


def test_filled() -> None:
    assert Validator({}, {"nick": "filled"}).passes()  # absent -> passes
    assert Validator({"nick": "ada"}, {"nick": "filled"}).passes()
    assert Validator({"nick": ""}, {"nick": "filled"}).fails()  # present but empty -> fails


def test_present() -> None:
    assert Validator({"nick": None}, {"nick": "present"}).passes()  # present, even if None
    assert Validator({}, {"nick": "present"}).fails()  # absent -> fails


def test_prohibited() -> None:
    assert Validator({}, {"promo": "prohibited"}).passes()
    assert Validator({"promo": "x"}, {"promo": "prohibited"}).fails()


def test_prohibited_if() -> None:
    rules = {"reason": "prohibited_if:status,active"}
    assert Validator({"status": "active"}, rules).passes()  # absent -> ok
    assert Validator({"status": "active", "reason": "x"}, rules).fails()
    assert Validator({"status": "closed", "reason": "x"}, rules).passes()  # condition off


def test_prohibited_unless() -> None:
    rules = {"override": "prohibited_unless:role,admin"}
    assert Validator({"role": "user"}, rules).passes()
    assert Validator({"role": "user", "override": "x"}, rules).fails()
    assert Validator({"role": "admin", "override": "x"}, rules).passes()


def test_required_if() -> None:
    rules = {"other_reason": "required_if:reason,other"}
    assert Validator({"reason": "other"}, rules).fails()
    assert Validator({"reason": "other", "other_reason": "x"}, rules).passes()
    assert Validator({"reason": "spam"}, rules).passes()  # condition off, not required


def test_required_unless() -> None:
    rules = {"phone": "required_unless:contact,email"}
    assert Validator({"contact": "sms"}, rules).fails()
    assert Validator({"contact": "email"}, rules).passes()  # condition off
    assert Validator({"contact": "sms", "phone": "555"}, rules).passes()


def test_required_with() -> None:
    rules = {"last": "required_with:first"}
    assert Validator({"first": "Ada"}, rules).fails()
    assert Validator({"first": "Ada", "last": "L"}, rules).passes()
    assert Validator({}, rules).passes()  # neither present


def test_required_with_all() -> None:
    rules = {"c": "required_with_all:a,b"}
    assert Validator({"a": 1, "b": 2}, rules).fails()
    assert Validator({"a": 1}, rules).passes()  # only one of a/b present -> not required
    assert Validator({"a": 1, "b": 2, "c": 3}, rules).passes()


def test_required_without() -> None:
    rules = {"email_field": "required_without:phone"}
    assert Validator({}, rules).fails()
    assert Validator({"phone": "555"}, rules).passes()
    assert Validator({"email_field": "a@b.com"}, rules).passes()


def test_required_without_all() -> None:
    rules = {"fallback": "required_without_all:a,b"}
    assert Validator({}, rules).fails()
    assert Validator({"a": 1}, rules).passes()  # one present -> not required
    assert Validator({"fallback": "x"}, rules).passes()


def test_accepted_if() -> None:
    rules = {"tos": "accepted_if:region,eu"}
    assert Validator({"region": "eu"}, rules).fails()
    assert Validator({"region": "eu", "tos": "yes"}, rules).passes()
    assert Validator({"region": "us"}, rules).passes()  # condition off


def test_declined() -> None:
    assert Validator({"opt_out": "no"}, {"opt_out": "declined"}).passes()
    assert Validator({"opt_out": "yes"}, {"opt_out": "declined"}).fails()


def test_declined_if() -> None:
    rules = {"newsletter": "declined_if:region,eu"}
    assert Validator({"region": "eu", "newsletter": "yes"}, rules).fails()
    assert Validator({"region": "eu", "newsletter": "no"}, rules).passes()
    assert Validator({"region": "us", "newsletter": "yes"}, rules).passes()


def test_conditional_reacts_to_dot_nested_sibling() -> None:
    rules = {"user.phone": "required_if:user.contact,phone"}
    data = {"user": {"contact": "phone"}}
    assert Validator(data, rules).fails()
    data_ok = {"user": {"contact": "phone", "phone": "555"}}
    assert Validator(data_ok, rules).passes()


def test_conditional_reacts_to_wildcard_sibling() -> None:
    # required_if keyed per resolved index via the wildcard expansion
    rules = {"items.*.qty": "required_if:items.*.active,yes"}
    data = {"items": [{"active": "yes", "qty": 2}, {"active": "yes"}]}
    v = Validator(data, rules)
    assert v.fails()
    assert "items.1.qty" in v.errors()
    assert "items.0.qty" not in v.errors()


def test_exclude_drops_field_from_validated() -> None:
    v = Validator({"a": 1, "b": 2}, {"a": "exclude", "b": "required"})
    assert v.passes()
    assert v.validated() == {"b": 2}


def test_exclude_if_conditionally_drops_field() -> None:
    v_dropped = Validator({"type": "guest", "email": "x"}, {"email": "exclude_if:type,guest"})
    assert v_dropped.passes()
    assert v_dropped.validated() == {}

    v_kept = Validator({"type": "member", "email": "x"}, {"email": "exclude_if:type,guest"})
    assert v_kept.passes()
    assert v_kept.validated() == {"email": "x"}


def test_exclude_unless_conditionally_drops_field() -> None:
    v_dropped = Validator({"role": "user", "note": "x"}, {"note": "exclude_unless:role,admin"})
    assert v_dropped.passes()
    assert v_dropped.validated() == {}

    v_kept = Validator({"role": "admin", "note": "x"}, {"note": "exclude_unless:role,admin"})
    assert v_kept.passes()
    assert v_kept.validated() == {"note": "x"}


def test_bail_stops_this_fields_rules_at_first_failure() -> None:
    v = Validator({"x": ""}, {"x": "bail|required|email"})
    assert v.fails()
    assert v.errors()["x"] == ["The x field is required."]  # only ONE error, not both


def test_without_bail_collects_all_failures() -> None:
    v = Validator({"x": ""}, {"x": "required|email"})
    assert v.fails()
    assert len(v.errors()["x"]) == 2  # both `required` and `email` failed


def test_stop_on_first_failure_halts_the_whole_pass() -> None:
    v = Validator(
        {"a": "", "b": ""}, {"a": "required", "b": "required"}, stop_on_first_failure=True
    )
    assert v.fails()
    assert "a" in v.errors()
    assert "b" not in v.errors()  # never reached


def test_without_stop_on_first_failure_checks_every_field() -> None:
    v = Validator({"a": "", "b": ""}, {"a": "required", "b": "required"})
    assert v.fails()
    assert "a" in v.errors()
    assert "b" in v.errors()
