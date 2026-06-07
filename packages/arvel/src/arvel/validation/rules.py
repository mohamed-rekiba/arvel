"""Laravel-style string validation rules."""

from __future__ import annotations

import asyncio
import ipaddress
import json as _json
import re
import uuid as _uuid
from collections.abc import Awaitable, Callable, Mapping, Sized
from typing import Any, cast

from sqlalchemy import column, select
from sqlalchemy.sql import TableClause
from sqlalchemy.sql import table as sqla_table
from sqlalchemy.sql.elements import ColumnClause

from arvel.database.session import get_active_session

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE_COLUMN_COUNT = 2
_EXCEPT_VALUE_INDEX = 2
_EXCEPT_COLUMN_INDEX = 3
_JPEG_MARKER_BYTE = 0xFF
_MIN_PNG_BYTES = 24
_BETWEEN_PARAM_COUNT = 2
_MIN_JPEG_SEGMENT_LENGTH = 2
_JPEG_SOI = 0xD8
_JPEG_EOI = 0xD9
_JPEG_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)

_MIME_BY_EXTENSION: dict[str, frozenset[str]] = {
    "jpg": frozenset({"image/jpeg", "image/jpg"}),
    "jpeg": frozenset({"image/jpeg", "image/jpg"}),
    "png": frozenset({"image/png"}),
    "gif": frozenset({"image/gif"}),
    "webp": frozenset({"image/webp"}),
}

RuleHandler = Callable[
    [str, object, list[str], Mapping[str, object], Any | None],
    str | None | Awaitable[str | None],
]


def parse_rule_expression(expression: str) -> tuple[str, list[str]]:
    """Split ``exists:posts,id`` into ``("exists", ["posts", "id"])``."""
    name, _, raw_params = expression.partition(":")
    params = [part.strip() for part in raw_params.split(",") if part.strip()] if raw_params else []
    return name.strip(), params


def _validate_identifier(name: str, label: str) -> None:
    if not _IDENTIFIER.match(name):
        msg = f"Invalid SQL {label} {name!r}."
        raise ValueError(msg)


def _table_clause(table_name: str, *column_names: str) -> TableClause:
    _validate_identifier(table_name, "table")
    for col_name in column_names:
        _validate_identifier(col_name, "column")
    columns: list[ColumnClause[Any]] = [column(col_name) for col_name in column_names]
    return sqla_table(table_name, *columns)


async def _matching_row_exists(table: str, column: str, value: object) -> bool:
    tbl = _table_clause(table, column)
    session = get_active_session()
    stmt = select(1).select_from(tbl).where(tbl.c[column] == value).limit(1)
    return (await session.execute(stmt)).first() is not None


async def _conflicting_row_exists(
    table: str,
    column: str,
    value: object,
    except_column: str,
    except_value: object,
) -> bool:
    tbl = _table_clause(table, column, except_column)
    session = get_active_session()
    stmt = (
        select(1)
        .select_from(tbl)
        .where(tbl.c[column] == value, tbl.c[except_column] != except_value)
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


async def _read_bytes(value: object) -> bytes | None:
    if isinstance(value, bytes | bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    read = getattr(value, "read", None)
    if callable(read):
        payload = read()
        if asyncio.iscoroutine(payload):
            payload = await payload
        if isinstance(payload, bytes | bytearray):
            return bytes(payload)
    return None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    index = 2
    while index < len(data):
        if data[index] != _JPEG_MARKER_BYTE:
            return None
        marker = data[index + 1]
        index += 2
        if marker in {_JPEG_SOI, _JPEG_EOI}:
            continue
        if index + 1 >= len(data):
            return None
        segment_length = int.from_bytes(data[index : index + 2], "big")
        if segment_length < _MIN_JPEG_SEGMENT_LENGTH:
            return None
        if marker in _JPEG_SOF_MARKERS:
            if index + 7 >= len(data):
                return None
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += segment_length
    return None


def _image_size(data: bytes) -> tuple[int, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= _MIN_PNG_BYTES:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return width, height
    if data.startswith(b"\xff\xd8"):
        return _jpeg_size(data)
    return None


def _parse_dimension_constraints(params: list[str]) -> dict[str, int]:
    constraints: dict[str, int] = {}
    for param in params:
        key, _, raw_value = param.partition("=")
        if not key or not raw_value:
            msg = f"Invalid dimensions parameter {param!r}."
            raise ValueError(msg)
        constraints[key.strip()] = int(raw_value)
    return constraints


def _dimension_violation(
    field: str, width: int, height: int, constraints: dict[str, int]
) -> str | None:
    specs: tuple[tuple[str, int, str, str], ...] = (
        ("min_width", width, "lt", "at least {0} pixels wide"),
        ("max_width", width, "gt", "at most {0} pixels wide"),
        ("min_height", height, "lt", "at least {0} pixels tall"),
        ("max_height", height, "gt", "at most {0} pixels tall"),
        ("width", width, "ne", "exactly {0} pixels wide"),
        ("height", height, "ne", "exactly {0} pixels tall"),
    )
    for key, actual, operator, template in specs:
        if key not in constraints:
            continue
        limit = constraints[key]
        failed = (
            (operator == "lt" and actual < limit)
            or (operator == "gt" and actual > limit)
            or (operator == "ne" and actual != limit)
        )
        if failed:
            return f"The {field} must be {template.format(limit)}."
    return None


async def rule_exists(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if len(params) < _TABLE_COLUMN_COUNT:
        return f"The {field} rule exists requires table and column."
    table, column = params[0], params[1]
    if not await _matching_row_exists(table, column, value):
        return f"The selected {field} is invalid."
    return None


async def rule_unique(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if len(params) < _TABLE_COLUMN_COUNT:
        return f"The {field} rule unique requires table and column."
    table, column = params[0], params[1]
    except_value = params[_EXCEPT_VALUE_INDEX] if len(params) > _EXCEPT_VALUE_INDEX else None
    except_column = params[_EXCEPT_COLUMN_INDEX] if len(params) > _EXCEPT_COLUMN_INDEX else "id"
    _validate_identifier(except_column, "column")
    conflict = (
        await _conflicting_row_exists(table, column, value, except_column, except_value)
        if except_value is not None
        else await _matching_row_exists(table, column, value)
    )
    if conflict:
        return f"The {field} has already been taken."
    return None


def rule_mimes(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params:
        return f"The {field} rule mimes requires at least one extension."
    allowed = {ext.lower().lstrip(".") for ext in params}
    filename = value if isinstance(value, str) else getattr(value, "filename", None)
    content_type = None if isinstance(value, str) else getattr(value, "content_type", None)
    extension = ""
    if isinstance(filename, str) and "." in filename:
        extension = filename.rsplit(".", 1)[-1].lower()
    ext_ok = extension in allowed
    mime_ok = False
    if isinstance(content_type, str):
        lowered = content_type.lower()
        mime_ok = any(lowered in _MIME_BY_EXTENSION.get(ext, frozenset()) for ext in allowed)
    if ext_ok or mime_ok:
        return None
    joined = ", ".join(sorted(allowed))
    return f"The {field} must be a file of type: {joined}."


def _is_empty_value(value: object) -> bool:
    return value in ("", [], {})


def rule_required(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None or _is_empty_value(value):
        return f"The {field} field is required."
    return None


def rule_digits(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params or not params[0].isdigit():
        return f"The {field} rule digits requires a length."
    expected = int(params[0])
    text = str(value)
    if len(text) == expected and text.isdigit():
        return None
    return f"The {field} must be {expected} digits."


async def rule_dimensions(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    raw = await _read_bytes(value)
    if raw is None:
        return f"The {field} must be an image."
    size = _image_size(raw)
    if size is None:
        return f"The {field} must be an image."
    width, height = size
    try:
        constraints = _parse_dimension_constraints(params)
    except ValueError as exc:
        return str(exc)
    return _dimension_violation(field, width, height, constraints)


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+\-.]*://[^\s]+$")
_ALPHA_RE = re.compile(r"^[A-Za-z]+$")
_ALPHA_NUM_RE = re.compile(r"^[A-Za-z0-9]+$")
_ALPHA_DASH_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

_TRUTHY = frozenset({True, "1", "true", "True", "TRUE", "yes", "Yes", "YES", "on", "On", "ON"})
_FALSY = frozenset({False, "0", "false", "False", "FALSE", "no", "No", "NO", "off", "Off", "OFF"})
_ACCEPTED = frozenset({True, "1", "true", "yes", "on"})


def _measure(value: object) -> float | None:
    """How big is a value? len() for strings/lists/dicts; the value itself for numbers."""
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(len(value))
    if isinstance(value, (list, tuple, dict, set)):
        sized = cast("Sized", value)
        return float(len(sized))
    return None


def rule_nullable(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = field, value, params, data, request
    return None  # always passes; presence-only marker for other rules


def rule_present(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = value, params, request
    if field not in data:
        return f"The {field} field must be present."
    return None


def rule_filled(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, request
    if field not in data:
        return None
    if value is None or _is_empty_value(value):
        return f"The {field} field must have a value."
    return None


def rule_prohibited(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, request
    if field in data and value is not None and not _is_empty_value(value):
        return f"The {field} field is prohibited."
    return None


def rule_string(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None or isinstance(value, str):
        return None
    return f"The {field} must be a string."


def rule_integer(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, bool):
        return f"The {field} must be an integer."
    if isinstance(value, int):
        return None
    if isinstance(value, str):
        try:
            int(value)
        except ValueError:
            pass
        else:
            return None
    return f"The {field} must be an integer."


def rule_numeric(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, bool):
        return f"The {field} must be a number."
    if isinstance(value, (int, float)):
        return None
    if isinstance(value, str):
        try:
            float(value)
        except ValueError:
            pass
        else:
            return None
    return f"The {field} must be a number."


def rule_boolean(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if value in _TRUTHY or value in _FALSY:
        return None
    return f"The {field} field must be true or false."


def rule_accepted(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value in _ACCEPTED:
        return None
    return f"The {field} must be accepted."


def rule_email(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str) and _EMAIL_RE.match(value):
        return None
    return f"The {field} must be a valid email address."


def rule_url(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str) and _URL_RE.match(value):
        return None
    return f"The {field} must be a valid URL."


def rule_uuid(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str):
        try:
            _uuid.UUID(value)
        except ValueError:
            pass
        else:
            return None
    return f"The {field} must be a valid UUID."


def rule_ip(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str):
        try:
            ipaddress.ip_address(value)
        except ValueError:
            pass
        else:
            return None
    return f"The {field} must be a valid IP address."


def rule_ipv4(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str):
        try:
            ipaddress.IPv4Address(value)
        except ValueError:
            pass
        else:
            return None
    return f"The {field} must be a valid IPv4 address."


def rule_ipv6(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str):
        try:
            ipaddress.IPv6Address(value)
        except ValueError:
            pass
        else:
            return None
    return f"The {field} must be a valid IPv6 address."


def rule_json(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str):
        try:
            _json.loads(value)
        except ValueError, TypeError:
            pass
        else:
            return None
    return f"The {field} must be a valid JSON string."


def rule_alpha(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str) and _ALPHA_RE.match(value):
        return None
    return f"The {field} must only contain letters."


def rule_alpha_num(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str) and _ALPHA_NUM_RE.match(value):
        return None
    return f"The {field} must only contain letters and numbers."


def rule_alpha_dash(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, data, request
    if value is None:
        return None
    if isinstance(value, str) and _ALPHA_DASH_RE.match(value):
        return None
    return f"The {field} must only contain letters, numbers, dashes and underscores."


def rule_regex(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params:
        return f"The {field} rule regex requires a pattern."
    pattern = ",".join(params)  # rejoin in case the pattern contains commas
    try:
        compiled = re.compile(pattern)
    except re.error:
        return f"The {field} rule regex pattern is invalid."
    if isinstance(value, str) and compiled.search(value):
        return None
    return f"The {field} format is invalid."


def rule_not_regex(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params:
        return f"The {field} rule not_regex requires a pattern."
    pattern = ",".join(params)
    try:
        compiled = re.compile(pattern)
    except re.error:
        return f"The {field} rule not_regex pattern is invalid."
    if isinstance(value, str) and not compiled.search(value):
        return None
    return f"The {field} format is invalid."


def rule_starts_with(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params:
        return f"The {field} rule starts_with requires at least one prefix."
    if isinstance(value, str) and any(value.startswith(p) for p in params):
        return None
    joined = ", ".join(params)
    return f"The {field} must start with one of: {joined}."


def rule_ends_with(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params:
        return f"The {field} rule ends_with requires at least one suffix."
    if isinstance(value, str) and any(value.endswith(p) for p in params):
        return None
    joined = ", ".join(params)
    return f"The {field} must end with one of: {joined}."


def rule_in(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    str_value = str(value)
    if str_value in params:
        return None
    joined = ", ".join(params)
    return f"The selected {field} is invalid. Allowed: {joined}."


def rule_not_in(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    str_value = str(value)
    if str_value not in params:
        return None
    return f"The selected {field} is invalid."


def rule_min(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params:
        return f"The {field} rule min requires a limit."
    try:
        limit = float(params[0])
    except ValueError:
        return f"The {field} rule min limit must be numeric."
    actual = _measure(value)
    if actual is None or actual >= limit:
        return None
    return f"The {field} must be at least {params[0]}."


def rule_max(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params:
        return f"The {field} rule max requires a limit."
    try:
        limit = float(params[0])
    except ValueError:
        return f"The {field} rule max limit must be numeric."
    actual = _measure(value)
    if actual is None or actual <= limit:
        return None
    return f"The {field} may not be greater than {params[0]}."


def rule_between(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if len(params) < _BETWEEN_PARAM_COUNT:
        return f"The {field} rule between requires min and max."
    try:
        low = float(params[0])
        high = float(params[1])
    except ValueError:
        return f"The {field} rule between limits must be numeric."
    actual = _measure(value)
    if actual is None or low <= actual <= high:
        return None
    return f"The {field} must be between {params[0]} and {params[1]}."


def rule_size(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = data, request
    if value is None:
        return None
    if not params:
        return f"The {field} rule size requires a limit."
    try:
        expected = float(params[0])
    except ValueError:
        return f"The {field} rule size limit must be numeric."
    actual = _measure(value)
    if actual is None or actual == expected:
        return None
    return f"The {field} must be size {params[0]}."


def rule_confirmed(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = params, request
    confirmation_key = f"{field}_confirmation"
    if data.get(confirmation_key) == value:
        return None
    return f"The {field} confirmation does not match."


def rule_same(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = request
    if not params:
        return f"The {field} rule same requires a field name."
    other = params[0]
    if data.get(other) == value:
        return None
    return f"The {field} and {other} must match."


def rule_different(
    field: str,
    value: object,
    params: list[str],
    data: Mapping[str, object],
    request: Any | None,
) -> str | None:
    _ = request
    if not params:
        return f"The {field} rule different requires a field name."
    other = params[0]
    if data.get(other) != value:
        return None
    return f"The {field} and {other} must be different."


RULE_HANDLERS: dict[str, RuleHandler] = {
    "accepted": rule_accepted,
    "alpha": rule_alpha,
    "alpha_dash": rule_alpha_dash,
    "alpha_num": rule_alpha_num,
    "between": rule_between,
    "boolean": rule_boolean,
    "confirmed": rule_confirmed,
    "different": rule_different,
    "digits": rule_digits,
    "dimensions": rule_dimensions,
    "email": rule_email,
    "ends_with": rule_ends_with,
    "exists": rule_exists,
    "filled": rule_filled,
    "in": rule_in,
    "integer": rule_integer,
    "ip": rule_ip,
    "ipv4": rule_ipv4,
    "ipv6": rule_ipv6,
    "json": rule_json,
    "max": rule_max,
    "mimes": rule_mimes,
    "min": rule_min,
    "not_in": rule_not_in,
    "not_regex": rule_not_regex,
    "nullable": rule_nullable,
    "numeric": rule_numeric,
    "present": rule_present,
    "prohibited": rule_prohibited,
    "regex": rule_regex,
    "required": rule_required,
    "same": rule_same,
    "size": rule_size,
    "starts_with": rule_starts_with,
    "string": rule_string,
    "unique": rule_unique,
    "url": rule_url,
    "uuid": rule_uuid,
}
