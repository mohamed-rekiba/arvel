"""Laravel-style string validation rules."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

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


RULE_HANDLERS: dict[str, RuleHandler] = {
    "digits": rule_digits,
    "dimensions": rule_dimensions,
    "exists": rule_exists,
    "mimes": rule_mimes,
    "required": rule_required,
    "unique": rule_unique,
}
