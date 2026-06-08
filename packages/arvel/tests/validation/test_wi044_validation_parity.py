"""bail, conditional-presence, date rules, custom registration, and Rule builders."""

from __future__ import annotations

from datetime import date

from arvel.validation import Rule, Validator, register_rule
from arvel.validation.rules import RULE_HANDLERS


class TestBail:
    async def test_stops_field_at_first_failure(self) -> None:
        data = {"code": "x"}
        details = await Validator(data).validate({"code": "bail|integer|min:5"})
        # Without bail both integer and min would fire; bail keeps only the first.
        assert len(details) == 1
        assert "integer" in details[0]["issue"]

    async def test_without_bail_collects_all_failures(self) -> None:
        data = {"code": "x"}
        details = await Validator(data).validate({"code": "integer|digits:3"})
        assert len(details) == 2

    async def test_bail_passes_when_no_failures(self) -> None:
        data = {"code": "12345"}
        details = await Validator(data).validate({"code": "bail|integer|min:3"})
        assert details == []


class TestRequiredIfUnless:
    async def test_required_if_triggers(self) -> None:
        data = {"kind": "card"}
        details = await Validator(data).validate({"number": "required_if:kind,card"})
        assert len(details) == 1
        assert details[0]["field"] == "number"

    async def test_required_if_skips_when_other_differs(self) -> None:
        data = {"kind": "cash"}
        details = await Validator(data).validate({"number": "required_if:kind,card"})
        assert details == []

    async def test_required_unless_triggers(self) -> None:
        data = {"kind": "cash"}
        details = await Validator(data).validate({"number": "required_unless:kind,card,wire"})
        assert len(details) == 1

    async def test_required_unless_skips_when_other_matches(self) -> None:
        data = {"kind": "wire"}
        details = await Validator(data).validate({"number": "required_unless:kind,card,wire"})
        assert details == []


class TestRequiredWithWithout:
    async def test_required_with_any_present(self) -> None:
        data = {"first": "a"}
        details = await Validator(data).validate({"last": "required_with:first,middle"})
        assert len(details) == 1

    async def test_required_with_all_needs_every_field(self) -> None:
        data = {"first": "a"}
        details = await Validator(data).validate({"last": "required_with_all:first,middle"})
        assert details == []

    async def test_required_without_any_missing(self) -> None:
        data = {"first": "a"}
        details = await Validator(data).validate({"phone": "required_without:email"})
        assert len(details) == 1

    async def test_required_without_all_satisfied_when_one_present(self) -> None:
        data = {"email": "a@b.co"}
        details = await Validator(data).validate({"phone": "required_without_all:email,sms"})
        assert details == []


class TestDateRules:
    async def test_date_accepts_iso_and_date_objects(self) -> None:
        assert await Validator({"d": "2026-01-15"}).validate({"d": "date"}) == []
        assert await Validator({"d": date(2026, 1, 15)}).validate({"d": "date"}) == []

    async def test_date_rejects_garbage(self) -> None:
        details = await Validator({"d": "not-a-date"}).validate({"d": "date"})
        assert len(details) == 1

    async def test_date_format_matches(self) -> None:
        assert await Validator({"d": "15/01/2026"}).validate({"d": "date_format:%d/%m/%Y"}) == []
        details = await Validator({"d": "2026-01-15"}).validate({"d": "date_format:%d/%m/%Y"})
        assert len(details) == 1

    async def test_before_and_after_literals(self) -> None:
        assert await Validator({"d": "2026-01-01"}).validate({"d": "before:2026-06-01"}) == []
        assert await Validator({"d": "2026-09-01"}).validate({"d": "after:2026-06-01"}) == []
        late = await Validator({"d": "2026-09-01"}).validate({"d": "before:2026-06-01"})
        assert len(late) == 1

    async def test_before_after_compare_against_another_field(self) -> None:
        data = {"start": "2026-01-01", "end": "2025-12-01"}
        details = await Validator(data).validate({"end": "after:start"})
        assert len(details) == 1

    async def test_before_or_equal_boundary(self) -> None:
        assert (
            await Validator({"d": "2026-06-01"}).validate({"d": "before_or_equal:2026-06-01"}) == []
        )
        assert (
            await Validator({"d": "2026-06-01"}).validate({"d": "after_or_equal:2026-06-01"}) == []
        )


class TestCustomRegistration:
    async def test_register_and_use_custom_rule(self) -> None:
        def rule_even(
            field: str, value: object, params: list[str], data: object, request: object
        ) -> str | None:
            _ = params, data, request
            if isinstance(value, int) and value % 2 == 0:
                return None
            return f"The {field} must be even."

        register_rule("even", rule_even)
        try:
            assert await Validator({"n": 4}).validate({"n": "even"}) == []
            details = await Validator({"n": 3}).validate({"n": "even"})
            assert len(details) == 1
            assert "even" in details[0]["issue"]
        finally:
            RULE_HANDLERS.pop("even", None)


class TestRuleBuilders:
    def test_in_and_not_in(self) -> None:
        assert Rule.in_("a", "b", "c") == "in:a,b,c"
        assert Rule.not_in(1, 2) == "not_in:1,2"

    def test_unique_with_and_without_ignore(self) -> None:
        assert Rule.unique("users", "email") == "unique:users,email"
        assert Rule.unique("users", "email", ignore=5) == "unique:users,email,5,id"
        assert Rule.unique("users", "email", ignore=5, id_column="uuid") == (
            "unique:users,email,5,uuid"
        )

    def test_exists_and_required_if(self) -> None:
        assert Rule.exists("posts", "id") == "exists:posts,id"
        assert Rule.required_if("kind", "card") == "required_if:kind,card"
        assert Rule.required_unless("kind", "card", "wire") == "required_unless:kind,card,wire"

    async def test_builder_output_runs_through_validator(self) -> None:
        details = await Validator({"role": "root"}).validate({"role": Rule.in_("admin", "user")})
        assert len(details) == 1
        ok = await Validator({"role": "admin"}).validate({"role": Rule.in_("admin", "user")})
        assert ok == []
