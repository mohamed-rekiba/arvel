"""arvel.validation.rules — the doc-10 rule-breadth expansion (story 12 VALID-RULES).

Split out of ``validation/__init__.py`` once the ``match`` in ``Validator._check`` would have
grown past ~120 cases (spec 12 §"split into rules.py if the match-statement grows unwieldy").
This module only holds *pure* rule checks — value + arg in, pass/fail out — that read at most a
sibling field off ``validator.data``. Rules that mutate the ``Validator``'s own state
(``exclude*`` → ``_excluded``, ``dimensions`` → needs the file-rules' PIL guard) stay on
``Validator`` itself in ``__init__.py``, next to ``file``/``image``/``mimes``.

``check()`` returns ``None`` for a rule name it doesn't own — the caller (``Validator._check``'s
``case _:``) then falls through to strict-mode / no-op handling, so ``UnknownValidationRule``
still fires on a typo'd rule name from *either* module.
"""

from __future__ import annotations

import re
from functools import cache
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from arvel.validation import Validator

# Crockford base32, first char 0-7 (ULID's 48-bit timestamp component).
_ULID = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$", re.IGNORECASE)
_MAC = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def _is_number(value: str) -> bool:
    """Local copy of ``__init__.py``'s numeric-string check — kept private to each module
    rather than exported across the split (pyright flags cross-module `_private` access)."""
    try:
        float(value)
    except ValueError:
        return False
    return True


def _filled(data: Any, path: str) -> bool:
    """``path`` is present in ``data`` (dot-aware) and its value isn't empty."""
    from arvel.support.helpers import Arr, data_get

    return Arr.has(data, path) and data_get(data, path) not in (None, "", [], {})


@cache
def _timezones() -> frozenset[str]:
    from zoneinfo import available_timezones

    return frozenset(available_timezones())


def _check_ip(value: Any, *, version: int) -> bool:
    if not isinstance(value, str):
        return False
    import ipaddress

    try:
        (ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address)(value)
    except ValueError:
        return False
    return True


def _check_decimal(value: Any, arg: str) -> bool:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return False
    text = str(value)
    if not _is_number(text):
        return False
    places = len(text.split(".", 1)[1]) if "." in text else 0
    low, _, high = arg.partition(",")
    lo = int(low)
    hi = int(high) if high else lo
    return lo <= places <= hi


def _check_multiple_of(value: Any, arg: str) -> bool:
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int, float))
        or not _is_number(str(value))
    ):
        return False
    divisor = float(arg)
    if divisor == 0:
        return False
    remainder = float(value) % divisor
    return abs(remainder) < 1e-9 or abs(remainder - divisor) < 1e-9


def _upload_extension(value: Any) -> str:
    name = str(getattr(value, "filename", "") or getattr(value, "client_name", ""))
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def check(validator: Validator, rule: str, value: Any, arg: str, field: str) -> bool | None:
    """Dispatch the story-12 rule set; ``None`` means "not one of mine"."""
    from arvel.support.helpers import Arr, data_get

    data = validator.data
    match rule:
        # -- presence / conditional ------------------------------------------------------
        case "present":
            return Arr.has(data, field)
        case "filled":
            return not Arr.has(data, field) or value not in (None, "", [], {})
        case "prohibited":
            return value in (None, "", [], {})
        case "prohibited_if":
            other, _, val = arg.partition(",")
            return value in (None, "", [], {}) if str(data_get(data, other)) == val else True
        case "prohibited_unless":
            other, _, val = arg.partition(",")
            return value in (None, "", [], {}) if str(data_get(data, other)) != val else True
        case "required_if":
            other, _, val = arg.partition(",")
            return value not in (None, "", [], {}) if str(data_get(data, other)) == val else True
        case "required_unless":
            other, _, val = arg.partition(",")
            return value not in (None, "", [], {}) if str(data_get(data, other)) != val else True
        case "required_with":
            others = arg.split(",")
            required = any(_filled(data, o) for o in others)
            return value not in (None, "", [], {}) if required else True
        case "required_with_all":
            others = arg.split(",")
            required = all(_filled(data, o) for o in others)
            return value not in (None, "", [], {}) if required else True
        case "required_without":
            others = arg.split(",")
            required = any(not _filled(data, o) for o in others)
            return value not in (None, "", [], {}) if required else True
        case "required_without_all":
            others = arg.split(",")
            required = all(not _filled(data, o) for o in others)
            return value not in (None, "", [], {}) if required else True
        case "accepted_if":
            other, _, val = arg.partition(",")
            accepted = value in (True, "yes", "on", 1, "1", "true")
            return accepted if str(data_get(data, other)) == val else True
        case "declined":
            return value in (False, "no", "off", 0, "0", "false")
        case "declined_if":
            other, _, val = arg.partition(",")
            declined = value in (False, "no", "off", 0, "0", "false")
            return declined if str(data_get(data, other)) == val else True

        # -- strings ----------------------------------------------------------------------
        case "uppercase":
            return isinstance(value, str) and value == value.upper()
        case "lowercase":
            return isinstance(value, str) and value == value.lower()
        case "ascii":
            return isinstance(value, str) and value.isascii()
        case "ulid":
            return isinstance(value, str) and bool(_ULID.match(value))
        case "not_regex":
            return isinstance(value, str) and not re.search(arg, value)
        case "doesnt_start_with":
            return isinstance(value, str) and not value.startswith(tuple(arg.split(",")))
        case "doesnt_end_with":
            return isinstance(value, str) and not value.endswith(tuple(arg.split(",")))
        case "contains":
            if not isinstance(value, (list, tuple)):
                return False
            haystack = [str(v) for v in cast("list[Any]", value)]
            return all(needle in haystack for needle in arg.split(","))

        # -- numbers ------------------------------------------------------------------------
        case "decimal":
            return _check_decimal(value, arg)
        case "multiple_of":
            return _check_multiple_of(value, arg)
        case "min_digits":
            return str(value).isdigit() and len(str(value)) >= int(arg)
        case "max_digits":
            return str(value).isdigit() and len(str(value)) <= int(arg)

        # -- types / formats ------------------------------------------------------------------
        case "timezone":
            return isinstance(value, str) and value in _timezones()
        case "ipv4":
            return _check_ip(value, version=4)
        case "ipv6":
            return _check_ip(value, version=6)
        case "mac_address":
            return isinstance(value, str) and bool(_MAC.match(value))

        # -- arrays -----------------------------------------------------------------------------
        case "in_array":
            other = data_get(data, arg)
            return isinstance(other, list) and value in other
        case "list":
            return isinstance(value, (list, tuple))

        # -- files (metadata only — `dimensions` needs bytes; stays on Validator) ----------------
        case "mimetypes":
            content_type = str(getattr(value, "content_type", "")).lower()
            return content_type in [m.strip().lower() for m in arg.split(",")]
        case "extensions":
            return _upload_extension(value) in [e.strip().lower() for e in arg.split(",")]

        case _:
            return None
