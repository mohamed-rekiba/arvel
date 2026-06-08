"""Nested and wildcard validation paths (items.*.id, address.city, explicit indices)."""

from __future__ import annotations

from arvel.validation import Validator
from arvel.validation.validator import resolve_targets


class TestResolveTargets:
    def test_plain_field_present_and_missing(self) -> None:
        assert resolve_targets("name", {"name": "x"}) == [("name", "x", True)]
        assert resolve_targets("name", {}) == [("name", None, False)]

    def test_dotted_path_resolves_nested(self) -> None:
        data: dict[str, object] = {"address": {"city": "Cairo"}}
        assert resolve_targets("address.city", data) == [("address.city", "Cairo", True)]

    def test_dotted_path_missing_still_yields_one_target(self) -> None:
        assert resolve_targets("address.city", {}) == [("address.city", None, False)]
        assert resolve_targets("address.city", {"address": {}}) == [("address.city", None, False)]

    def test_wildcard_over_list(self) -> None:
        data: dict[str, object] = {"items": [{"id": 1}, {"id": 2}]}
        assert resolve_targets("items.*.id", data) == [
            ("items.0.id", 1, True),
            ("items.1.id", 2, True),
        ]

    def test_wildcard_missing_collection_yields_nothing(self) -> None:
        assert resolve_targets("items.*.id", {}) == []
        assert resolve_targets("items.*.id", {"items": "notalist"}) == []

    def test_wildcard_over_dict(self) -> None:
        data: dict[str, object] = {"meta": {"a": {"v": 1}, "b": {"v": 2}}}
        targets = resolve_targets("meta.*.v", data)
        assert ("meta.a.v", 1, True) in targets
        assert ("meta.b.v", 2, True) in targets

    def test_explicit_list_index(self) -> None:
        data: dict[str, object] = {"items": [{"id": 9}]}
        assert resolve_targets("items.0.id", data) == [("items.0.id", 9, True)]


class TestWildcardValidation:
    async def test_each_element_validated(self) -> None:
        data: dict[str, object] = {"items": [{"id": 1}, {}]}
        details = await Validator(data).validate({"items.*.id": "required|integer"})
        assert len(details) == 1
        assert details[0]["field"] == "items.1.id"

    async def test_all_valid_passes(self) -> None:
        data: dict[str, object] = {"items": [{"id": 1}, {"id": 2}]}
        details = await Validator(data).validate({"items.*.id": "required|integer"})
        assert details == []

    async def test_type_rule_on_each_element(self) -> None:
        data: dict[str, object] = {"items": [{"qty": "x"}, {"qty": 3}]}
        details = await Validator(data).validate({"items.*.qty": "integer"})
        assert len(details) == 1
        assert details[0]["field"] == "items.0.qty"

    async def test_missing_array_skips(self) -> None:
        details = await Validator({}).validate({"items.*.id": "required"})
        assert details == []


class TestNestedValidation:
    async def test_nested_required_missing_child(self) -> None:
        data: dict[str, object] = {"address": {"zip": "11111"}}
        details = await Validator(data).validate({"address.city": "required"})
        assert len(details) == 1
        assert details[0]["field"] == "address.city"

    async def test_nested_required_missing_parent(self) -> None:
        details = await Validator({}).validate({"address.city": "required"})
        assert len(details) == 1
        assert details[0]["field"] == "address.city"

    async def test_nested_present_rule_is_path_aware(self) -> None:
        # present should pass when the leaf exists, even though data is "flat" elsewhere.
        ok = await Validator({"address": {"city": "Cairo"}}).validate({"address.city": "present"})
        assert ok == []
        missing = await Validator({"address": {}}).validate({"address.city": "present"})
        assert len(missing) == 1

    async def test_nested_filled_skips_when_absent(self) -> None:
        details = await Validator({"address": {}}).validate({"address.city": "filled"})
        assert details == []


class TestMessagesAndAttributes:
    async def test_wildcard_message_override(self) -> None:
        data: dict[str, object] = {"items": [{}]}
        v = Validator(data, messages={"items.*.id.required": "Each item needs an id."})
        details = await v.validate({"items.*.id": "required"})
        assert details[0]["issue"] == "Each item needs an id."

    async def test_concrete_path_message_override_wins(self) -> None:
        data: dict[str, object] = {"items": [{}, {}]}
        v = Validator(
            data,
            messages={
                "items.*.id.required": "generic",
                "items.1.id.required": "specific for row 1",
            },
        )
        details = await v.validate({"items.*.id": "required"})
        issues = {d["field"]: d["issue"] for d in details}
        assert issues["items.0.id"] == "generic"
        assert issues["items.1.id"] == "specific for row 1"


class TestBackwardCompatibility:
    async def test_flat_fields_unchanged(self) -> None:
        data = {"email": "bad", "age": "x"}
        details = await Validator(data).validate({"email": "email", "age": "integer"})
        fields = {d["field"] for d in details}
        assert fields == {"email", "age"}

    async def test_flat_attribute_label_substitution(self) -> None:
        v = Validator({"email": ""}, attributes={"email": "email address"})
        details = await v.validate({"email": "required"})
        assert "email address" in details[0]["issue"]
