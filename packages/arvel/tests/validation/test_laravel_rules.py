"""Tests for the Laravel-parity validation rule set added in WI-005."""

from __future__ import annotations

import pytest
from arvel.validation import Validator


async def _run(data: dict[str, object], rules: dict[str, str]) -> list[dict[str, str]]:
    return await Validator(data).validate(rules)


class TestNullable:
    @pytest.mark.asyncio
    async def test_always_passes(self) -> None:
        assert await _run({"a": None}, {"a": "nullable"}) == []
        assert await _run({"a": "x"}, {"a": "nullable"}) == []


class TestPresent:
    @pytest.mark.asyncio
    async def test_passes_when_present_even_if_null(self) -> None:
        assert await _run({"a": None}, {"a": "present"}) == []
        assert await _run({"a": ""}, {"a": "present"}) == []

    @pytest.mark.asyncio
    async def test_fails_when_absent(self) -> None:
        details = await _run({}, {"a": "present"})
        assert details[0]["issue"] == "The a field must be present."


class TestFilled:
    @pytest.mark.asyncio
    async def test_passes_when_absent(self) -> None:
        assert await _run({}, {"a": "filled"}) == []

    @pytest.mark.asyncio
    async def test_fails_when_present_but_empty(self) -> None:
        empties: tuple[object, ...] = (None, "", [], {})
        for empty in empties:
            details = await _run({"a": empty}, {"a": "filled"})
            assert details[0]["issue"] == "The a field must have a value."

    @pytest.mark.asyncio
    async def test_passes_when_present_with_value(self) -> None:
        assert await _run({"a": "x"}, {"a": "filled"}) == []


class TestProhibited:
    @pytest.mark.asyncio
    async def test_passes_when_absent_or_empty(self) -> None:
        assert await _run({}, {"a": "prohibited"}) == []
        assert await _run({"a": ""}, {"a": "prohibited"}) == []

    @pytest.mark.asyncio
    async def test_fails_when_present_with_value(self) -> None:
        details = await _run({"a": "x"}, {"a": "prohibited"})
        assert details[0]["issue"] == "The a field is prohibited."


class TestString:
    @pytest.mark.asyncio
    async def test_passes_for_strings_and_null(self) -> None:
        assert await _run({"a": "x"}, {"a": "string"}) == []
        assert await _run({"a": None}, {"a": "string"}) == []

    @pytest.mark.asyncio
    async def test_fails_for_non_strings(self) -> None:
        details = await _run({"a": 42}, {"a": "string"})
        assert details[0]["issue"] == "The a must be a string."


class TestInteger:
    @pytest.mark.asyncio
    async def test_passes_for_ints_and_numeric_strings(self) -> None:
        assert await _run({"a": 5}, {"a": "integer"}) == []
        assert await _run({"a": "5"}, {"a": "integer"}) == []

    @pytest.mark.asyncio
    async def test_fails_for_booleans_floats_and_non_numeric(self) -> None:
        for bad in (True, 1.5, "abc"):
            details = await _run({"a": bad}, {"a": "integer"})
            assert details and details[0]["issue"] == "The a must be an integer."


class TestNumeric:
    @pytest.mark.asyncio
    async def test_passes_for_numbers_and_numeric_strings(self) -> None:
        for good in (5, 1.5, "5", "1.5", "-3.14"):
            assert await _run({"a": good}, {"a": "numeric"}) == []

    @pytest.mark.asyncio
    async def test_fails_for_bools_and_non_numeric_strings(self) -> None:
        for bad in (True, "abc"):
            details = await _run({"a": bad}, {"a": "numeric"})
            assert details and details[0]["issue"] == "The a must be a number."


class TestBoolean:
    @pytest.mark.asyncio
    async def test_accepts_common_truthy_falsy(self) -> None:
        for good in (True, False, 1, 0, "1", "0", "true", "false", "yes", "no", "on", "off"):
            assert await _run({"a": good}, {"a": "boolean"}) == []

    @pytest.mark.asyncio
    async def test_rejects_other_values(self) -> None:
        details = await _run({"a": "maybe"}, {"a": "boolean"})
        assert details[0]["issue"] == "The a field must be true or false."


class TestAccepted:
    @pytest.mark.asyncio
    async def test_passes_only_for_truthy_form_values(self) -> None:
        for good in (True, 1, "1", "true", "yes", "on"):
            assert await _run({"a": good}, {"a": "accepted"}) == []
        for bad in (False, 0, "0", "no", None):
            details = await _run({"a": bad}, {"a": "accepted"})
            assert details and details[0]["issue"] == "The a must be accepted."


class TestEmail:
    @pytest.mark.asyncio
    async def test_accepts_valid_emails(self) -> None:
        for good in ("a@b.co", "first.last+tag@example.com", "x-y@sub.example.io"):
            assert await _run({"a": good}, {"a": "email"}) == []

    @pytest.mark.asyncio
    async def test_rejects_invalid_emails(self) -> None:
        for bad in ("notanemail", "@b.co", "a@", "a@b"):
            details = await _run({"a": bad}, {"a": "email"})
            assert details and "valid email" in details[0]["issue"]


class TestUrl:
    @pytest.mark.asyncio
    async def test_accepts_valid_urls(self) -> None:
        for good in ("https://example.com", "http://a.b/c?d=1", "ftp://files.example/"):
            assert await _run({"a": good}, {"a": "url"}) == []

    @pytest.mark.asyncio
    async def test_rejects_invalid_urls(self) -> None:
        details = await _run({"a": "not a url"}, {"a": "url"})
        assert details and "valid URL" in details[0]["issue"]


class TestUuid:
    @pytest.mark.asyncio
    async def test_accepts_valid_uuid(self) -> None:
        assert await _run({"a": "550e8400-e29b-41d4-a716-446655440000"}, {"a": "uuid"}) == []

    @pytest.mark.asyncio
    async def test_rejects_garbage(self) -> None:
        details = await _run({"a": "not-a-uuid"}, {"a": "uuid"})
        assert details and "valid UUID" in details[0]["issue"]


class TestIpRules:
    @pytest.mark.asyncio
    async def test_ip_accepts_both_families(self) -> None:
        assert await _run({"a": "192.168.1.1"}, {"a": "ip"}) == []
        assert await _run({"a": "::1"}, {"a": "ip"}) == []

    @pytest.mark.asyncio
    async def test_ipv4_rejects_v6(self) -> None:
        details = await _run({"a": "::1"}, {"a": "ipv4"})
        assert details and "IPv4" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_ipv6_rejects_v4(self) -> None:
        details = await _run({"a": "192.168.1.1"}, {"a": "ipv6"})
        assert details and "IPv6" in details[0]["issue"]


class TestJsonRule:
    @pytest.mark.asyncio
    async def test_accepts_valid_json(self) -> None:
        assert await _run({"a": '{"k": 1}'}, {"a": "json"}) == []
        assert await _run({"a": "[1, 2, 3]"}, {"a": "json"}) == []

    @pytest.mark.asyncio
    async def test_rejects_invalid_json(self) -> None:
        details = await _run({"a": "{not json}"}, {"a": "json"})
        assert details and "JSON" in details[0]["issue"]


class TestAlphaFamily:
    @pytest.mark.asyncio
    async def test_alpha(self) -> None:
        assert await _run({"a": "abcXYZ"}, {"a": "alpha"}) == []
        details = await _run({"a": "abc1"}, {"a": "alpha"})
        assert details and "only contain letters" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_alpha_num(self) -> None:
        assert await _run({"a": "abc123"}, {"a": "alpha_num"}) == []
        details = await _run({"a": "abc-123"}, {"a": "alpha_num"})
        assert details and "letters and numbers" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_alpha_dash(self) -> None:
        assert await _run({"a": "abc-123_xy"}, {"a": "alpha_dash"}) == []
        details = await _run({"a": "abc 123"}, {"a": "alpha_dash"})
        assert details and "dashes and underscores" in details[0]["issue"]


class TestRegexRules:
    @pytest.mark.asyncio
    async def test_regex_match(self) -> None:
        assert await _run({"a": "abc-1"}, {"a": r"regex:^[a-z]+-\d+$"}) == []
        details = await _run({"a": "ABC-1"}, {"a": r"regex:^[a-z]+-\d+$"})
        assert details and "format is invalid" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_not_regex(self) -> None:
        assert await _run({"a": "abc"}, {"a": r"not_regex:^\d+$"}) == []
        details = await _run({"a": "123"}, {"a": r"not_regex:^\d+$"})
        assert details and "format is invalid" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_regex_requires_pattern(self) -> None:
        details = await _run({"a": "x"}, {"a": "regex"})
        assert details and "requires a pattern" in details[0]["issue"]


class TestStartsEndsWith:
    @pytest.mark.asyncio
    async def test_starts_with(self) -> None:
        assert await _run({"a": "https://example.com"}, {"a": "starts_with:http://,https://"}) == []
        details = await _run({"a": "ftp://x"}, {"a": "starts_with:http://,https://"})
        assert details and "must start with" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_ends_with(self) -> None:
        assert await _run({"a": "report.pdf"}, {"a": "ends_with:.pdf,.docx"}) == []
        details = await _run({"a": "report.txt"}, {"a": "ends_with:.pdf,.docx"})
        assert details and "must end with" in details[0]["issue"]


class TestInNotIn:
    @pytest.mark.asyncio
    async def test_in(self) -> None:
        assert await _run({"role": "admin"}, {"role": "in:admin,user,guest"}) == []
        details = await _run({"role": "boss"}, {"role": "in:admin,user,guest"})
        assert details and "Allowed: admin, user, guest" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_not_in(self) -> None:
        assert await _run({"role": "viewer"}, {"role": "not_in:admin,owner"}) == []
        details = await _run({"role": "admin"}, {"role": "not_in:admin,owner"})
        assert details and "selected role is invalid" in details[0]["issue"]


class TestMinMaxBetweenSize:
    @pytest.mark.asyncio
    async def test_min_string_length(self) -> None:
        assert await _run({"a": "abcd"}, {"a": "min:3"}) == []
        details = await _run({"a": "ab"}, {"a": "min:3"})
        assert details and "at least 3" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_max_number_value(self) -> None:
        assert await _run({"a": 5}, {"a": "max:10"}) == []
        details = await _run({"a": 15}, {"a": "max:10"})
        assert details and "may not be greater than 10" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_between_list_length(self) -> None:
        assert await _run({"a": [1, 2, 3]}, {"a": "between:2,5"}) == []
        details = await _run({"a": [1]}, {"a": "between:2,5"})
        assert details and "between 2 and 5" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_size_exact(self) -> None:
        assert await _run({"a": "abcde"}, {"a": "size:5"}) == []
        details = await _run({"a": "abc"}, {"a": "size:5"})
        assert details and "must be size 5" in details[0]["issue"]


class TestConfirmedSameDifferent:
    @pytest.mark.asyncio
    async def test_confirmed(self) -> None:
        assert (
            await _run(
                {"password": "secret", "password_confirmation": "secret"},
                {"password": "confirmed"},
            )
            == []
        )
        details = await _run(
            {"password": "secret", "password_confirmation": "other"},
            {"password": "confirmed"},
        )
        assert details and "confirmation does not match" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_same(self) -> None:
        assert await _run({"a": "x", "b": "x"}, {"a": "same:b"}) == []
        details = await _run({"a": "x", "b": "y"}, {"a": "same:b"})
        assert details and "must match" in details[0]["issue"]

    @pytest.mark.asyncio
    async def test_different(self) -> None:
        assert await _run({"a": "x", "b": "y"}, {"a": "different:b"}) == []
        details = await _run({"a": "x", "b": "x"}, {"a": "different:b"})
        assert details and "must be different" in details[0]["issue"]
