"""arvel.validation — schema-first validation on **msgspec** (core; DR-0002).

``validate(data, Schema)`` coerces+validates a mapping into a typed ``msgspec.Struct``
(422 ``ValidationException`` on failure); ``json_schema(Schema)`` emits the JSON
schema Litestar feeds into OpenAPI (G4). ``FormRequest`` is a Struct base with
``parse``/``authorize``. msgspec is core. Grounded in knowledge/port/10-validation.md.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Self, cast

import msgspec

if TYPE_CHECKING:
    from collections.abc import Mapping, Sized


class Schema(msgspec.Struct):
    """arvel's typed-data base — subclass it for request bodies / DTOs instead of importing
    ``msgspec.Struct`` directly. ``validate(data, MySchema)`` decodes + validates into it, and its
    JSON schema feeds Litestar's OpenAPI. (A thin, arvel-native wrapper over the msgspec engine.)"""


class ValidationException(Exception):
    """Raised when input fails validation (rendered as HTTP 422 by the kernel)."""

    def __init__(self, errors: Any, status: int = 422) -> None:
        self.errors = errors
        self.status = status
        super().__init__(str(errors))


class UnknownValidationRule(Exception):
    """Raised in ``strict`` mode when a rule name isn't recognized (e.g. a typo like ``requried``).

    This is a *programmer* error — a misspelled or unsupported rule that would otherwise be a silent
    no-op — not a user-input failure, so it is deliberately NOT a ``ValidationException`` (no 422)."""

    def __init__(self, rule: str) -> None:
        self.rule = rule
        super().__init__(f"Unknown validation rule: {rule!r}")


class AuthorizationException(Exception):
    """Raised when a FormRequest's ``authorize()`` returns False (rendered as HTTP 403)."""

    def __init__(self, message: str = "This action is unauthorized.", status: int = 403) -> None:
        self.status = status
        super().__init__(message)


def validate[T: msgspec.Struct](
    data: Mapping[str, Any], schema: type[T], *, strict: bool = False
) -> T:
    """Validate+coerce ``data`` into ``schema`` (a msgspec Struct); raise on failure."""
    try:
        return msgspec.convert(dict(data), schema, strict=strict)
    except msgspec.ValidationError as exc:
        raise ValidationException(str(exc)) from exc


def json_schema(schema: type[msgspec.Struct]) -> dict[str, Any]:
    """The JSON schema for ``schema`` (what Litestar turns into OpenAPI)."""
    return msgspec.json.schema(schema)


class FormRequest(msgspec.Struct):
    """A validated request DTO: subclass with typed fields, then ``parse(data)``.

    Lifecycle hooks (override as needed; spec 10 §81): ``prepare_for_validation`` normalizes the
    raw input *before* validation, ``passed_validation`` runs *after* a successful parse.
    (Laravel's ``withValidator`` has no equivalent here — it belongs to the rule ``Validator``,
    which owns the rule engine and ``after`` hooks; the msgspec FormRequest stays type-driven.)
    """

    @classmethod
    def prepare_for_validation(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Hook: normalize/augment the raw input before validation (default: unchanged)."""
        return data

    def passed_validation(self) -> None:
        """Hook: run after a successful parse — derive/clean fields (default: no-op)."""

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> Self:
        instance = validate(cls.prepare_for_validation(dict(data)), cls)
        instance.passed_validation()
        return instance

    @classmethod
    def authorized(cls, data: Mapping[str, Any]) -> Self:
        """Validate (422 on bad input) then check ``authorize()`` (403 if denied)."""
        instance = cls.parse(data)
        if not instance.authorize():
            raise AuthorizationException()
        return instance

    def authorize(self) -> bool:
        return True


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

_DEFAULT_MESSAGES = {
    "required": "The {field} field is required.",
    "string": "The {field} must be a string.",
    "integer": "The {field} must be an integer.",
    "numeric": "The {field} must be a number.",
    "boolean": "The {field} field must be true or false.",
    "email": "The {field} must be a valid email address.",
    "url": "The {field} must be a valid URL.",
    "alpha": "The {field} may only contain letters.",
    "alpha_num": "The {field} may only contain letters and numbers.",
    "min": "The {field} must be at least {arg}.",
    "max": "The {field} may not be greater than {arg}.",
    "size": "The {field} must be {arg}.",
    "gt": "The {field} must be greater than {arg}.",
    "gte": "The {field} must be greater than or equal to {arg}.",
    "lt": "The {field} must be less than {arg}.",
    "lte": "The {field} must be less than or equal to {arg}.",
    "digits": "The {field} must be {arg} digits.",
    "digits_between": "The {field} must be between {arg} digits.",
    "alpha_dash": "The {field} may only contain letters, numbers, dashes and underscores.",
    "json": "The {field} must be a valid JSON string.",
    "ip": "The {field} must be a valid IP address.",
    "in": "The selected {field} is invalid.",
    "not_in": "The selected {field} is invalid.",
    "array": "The {field} must be an array.",
    "between": "The {field} must be between {arg}.",
    "starts_with": "The {field} must start with one of: {arg}.",
    "ends_with": "The {field} must end with one of: {arg}.",
    "uuid": "The {field} must be a valid UUID.",
    "date": "The {field} is not a valid date.",
    "date_format": "The {field} does not match the format {arg}.",
    "before": "The {field} must be a date before {arg}.",
    "after": "The {field} must be a date after {arg}.",
    "date_equals": "The {field} must be a date equal to {arg}.",
    "unique": "The {field} has already been taken.",
    "exists": "The selected {field} is invalid.",
    "confirmed": "The {field} confirmation does not match.",
    "same": "The {field} and {arg} must match.",
    "different": "The {field} and {arg} must be different.",
    "accepted": "The {field} must be accepted.",
    "regex": "The {field} format is invalid.",
    "file": "The {field} must be an uploaded file.",
    "image": "The {field} must be an image.",
    "mimes": "The {field} must be a file of type: {arg}.",
}


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _grow(lst: list[Any], idx: int) -> None:
    """Pad ``lst`` with ``None`` so index ``idx`` is assignable."""
    while len(lst) <= idx:
        lst.append(None)


def _descend(node: Any, seg: str, *, want_list: bool) -> Any:
    """Return (creating if needed) the child of ``node`` at ``seg`` — a list when ``want_list``
    (the next segment is an integer index), else a dict. Integer ``seg`` indexes a list node."""
    child: Any = [] if want_list else {}
    if isinstance(node, list):
        lst = cast("list[Any]", node)
        idx = int(seg)
        _grow(lst, idx)
        if not isinstance(lst[idx], (dict, list)):
            lst[idx] = child
        return lst[idx]
    existing: Any = cast("dict[str, Any]", node).get(seg)
    if isinstance(existing, (dict, list)):
        return cast("Any", existing)
    cast("dict[str, Any]", node)[seg] = child
    return child


def _assign_path(root: dict[str, Any], path: str, val: Any) -> None:
    """Set ``val`` at a dot-path into ``root``, creating nested dicts — and lists wherever the next
    segment is an integer index — so ``items.0.price`` rebuilds ``{"items": [{"price": ...}]}``.

    A purely-numeric segment is *always* treated as a list index (the cost of dot-notation: a literal
    digit-string dict key can't be told apart from an index). Sparse indices pad with ``None`` to keep
    array positions aligned, so a list in the result may contain ``None`` holes where a ruled leaf was
    absent from some elements."""
    segments = path.split(".")
    node: Any = root
    for depth in range(len(segments) - 1):
        node = _descend(node, segments[depth], want_list=segments[depth + 1].isdigit())
    last = segments[-1]
    if isinstance(node, list):
        lst = cast("list[Any]", node)
        idx = int(last)
        _grow(lst, idx)
        lst[idx] = val
    else:
        cast("dict[str, Any]", node)[last] = val


_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y")


def _parse_date(value: Any, fmt: str | None = None) -> Any:
    """Parse ``value`` to a ``datetime`` for the date rules. With ``fmt`` (Python ``strftime`` codes —
    arvel is Python, so date_format uses Python codes, not Laravel's PHP codes), only that format is
    accepted; without it, ISO 8601 then a few common formats are tried. Returns None on failure."""
    from datetime import datetime

    if not isinstance(value, str):
        return None
    if fmt is not None:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    for candidate in _DATE_FORMATS:
        try:
            return datetime.strptime(value, candidate)
        except ValueError:
            continue
    return None


class Rule:
    """Base for **custom rule objects** (doc 10). Subclass and implement ``passes``; the
    instance goes straight into a field's rule list, e.g. ``{"code": [Uppercase()]}``. On
    failure ``message`` is recorded (``:attribute`` is replaced with the field name)."""

    message: str = "The :attribute is invalid."

    async def passes(self, attribute: str, value: Any) -> bool:
        raise NotImplementedError(f"{type(self).__name__} must implement passes()")


class Validator:
    """Rule-based validation (Laravel ``Validator::make``).

    ``rules`` maps field → a ``|``-delimited string or list, e.g.
    ``{"email": "required|email", "age": "nullable|integer|min:18"}``. ``passes()``/
    ``fails()`` return booleans; ``validate()`` raises a 422 ``ValidationException``
    carrying an ``errors`` dict; ``messages`` overrides per ``rule`` or ``field.rule``.
    """

    def __init__(
        self,
        data: Mapping[str, Any],
        rules: Mapping[str, str | list[Any]],
        messages: Mapping[str, str] | None = None,
        connection: Any = None,
        *,
        strict: bool = False,
    ) -> None:
        self.data = dict(data)
        self.rules = rules
        self.messages = dict(messages or {})
        self._errors: dict[str, list[str]] = {}
        self._connection = connection  # for async DB rules (unique/exists)
        #: when True, an unrecognized rule name raises ``UnknownValidationRule`` instead of no-op'ing
        self.strict = strict

    def _parse_rules(self, ruleset: str | list[Any]) -> list[Any]:
        return (
            [r.strip() for r in ruleset.split("|")] if isinstance(ruleset, str) else list(ruleset)
        )

    def passes(self) -> bool:
        from arvel.support.helpers import data_get

        self._errors = {}
        for field, ruleset in self.rules.items():
            rules = self._parse_rules(ruleset)
            if "*" in field:  # nested array rule (items.*.price)
                self._validate_wildcard(field, rules)
                continue
            if "sometimes" in rules and field not in self.data:
                continue  # only validate when the field is present
            # data_get resolves dot-paths into nested dicts (Laravel: `user.email`), not just flat keys
            value = data_get(self.data, field)
            if value is None and "nullable" in rules:
                continue
            for rule in rules:
                if not isinstance(rule, str):  # custom Rule object → handled in passes_async
                    continue
                if rule in ("nullable", "sometimes"):
                    continue
                name, _, arg = rule.partition(":")
                if not self._check(name, value, arg, field):
                    self._errors.setdefault(field, []).append(self._message(field, name, arg))
        return not self._errors

    def _validate_wildcard(self, field: str, rules: list[Any]) -> None:
        """Apply rules to each element of a ``a.*.b`` path, keying errors by the resolved index."""
        from arvel.support.helpers import data_get

        values = data_get(self.data, field)
        if not isinstance(values, list):
            return
        for index, value in enumerate(cast("list[Any]", values)):
            key = field.replace("*", str(index), 1)
            for rule in rules:
                if not isinstance(rule, str):  # custom Rule object → handled in passes_async
                    continue
                if rule in ("nullable", "sometimes"):
                    continue
                name, _, arg = rule.partition(":")
                if not self._check(name, value, arg, key):
                    self._errors.setdefault(key, []).append(self._message(key, name, arg))

    def fails(self) -> bool:
        return not self.passes()

    async def passes_async(self) -> bool:
        """Run sync rules, then the async DB rules (``unique``/``exists``)."""
        from arvel.support.helpers import data_get

        self.passes()  # populates _errors from the synchronous rules first
        for field, ruleset in self.rules.items():
            rules = self._parse_rules(ruleset)
            if "sometimes" in rules and field not in self.data:
                continue
            value = data_get(self.data, field)
            if value is None and "nullable" in rules:
                continue
            for rule in rules:
                if isinstance(rule, Rule):  # custom rule object
                    if not await rule.passes(field, value):
                        message = rule.message.replace(":attribute", field)
                        self._errors.setdefault(field, []).append(message)
                    continue
                name, _, arg = rule.partition(":")
                if name in ("unique", "exists") and not await self._check_db(
                    name, value, arg, field
                ):
                    self._errors.setdefault(field, []).append(self._message(field, name, arg))
        return not self._errors

    async def fails_async(self) -> bool:
        return not await self.passes_async()

    async def validate_async(self) -> dict[str, Any]:
        if await self.fails_async():
            raise ValidationException(self._errors)
        return self.validated()

    async def _check_db(self, rule: str, value: Any, arg: str, field: str) -> bool:
        import sqlalchemy as sa

        from arvel.database import Builder

        resolver = self._resolve_connection()
        if resolver is None:  # no DB bound → can't assert; treat as satisfied
            return True
        table_name, _, column = arg.partition(",")
        column = column or field
        column_obj = cast("Any", sa.Column(column))  # NullType → no bind-param coercion
        table = sa.Table(table_name, sa.MetaData(), column_obj)
        count: int = await Builder(table, resolver).where(column, "=", value).count()
        return count == 0 if rule == "unique" else count > 0

    def _resolve_connection(self) -> Any:
        if self._connection is not None:
            return self._connection
        from arvel.kernel import app, has_application

        if has_application() and app().bound("db"):
            return app().make("db")
        return None

    def errors(self) -> dict[str, list[str]]:
        return self._errors

    def validated(self) -> dict[str, Any]:
        """The validated subset of the input, with nesting preserved (Laravel ``validated()``).

        Each rule's field is resolved by dot-path — so a ``user.email`` rule contributes the nested
        value it validated — and the result rebuilds that nesting (``{"user": {"email": ...}}``)
        rather than a flat ``"user.email"`` key. Wildcard rules (``items.*.price``) put each
        validated leaf back in its array position. A field absent from the input is omitted (so an
        absent ``sometimes`` field never appears); a present field whose value is ``None`` is kept.
        """
        from arvel.support.helpers import Arr, data_get

        result: dict[str, Any] = {}
        for field in self.rules:
            for path in self._concrete_paths(field):
                if Arr.has(self.data, path):
                    _assign_path(result, path, data_get(self.data, path))
        return result

    def _concrete_paths(self, field: str) -> list[str]:
        """Expand a wildcard rule (``items.*.price``) into the concrete dot-paths present in the
        data (``items.0.price`` …); a plain field yields just itself."""
        from arvel.support.helpers import data_get

        if "*" not in field:
            return [field]
        head, _, tail = field.partition(".*")
        container = data_get(self.data, head)
        if not isinstance(container, list):
            return []
        tail = tail.lstrip(".")
        paths: list[str] = []
        for index in range(len(cast("list[Any]", container))):
            base = f"{head}.{index}"
            paths.extend(self._concrete_paths(f"{base}.{tail}") if tail else [base])
        return paths

    def validate(self) -> dict[str, Any]:
        if self.fails():
            raise ValidationException(self._errors)
        return self.validated()

    def _has_numeric_rule(self, field: str) -> bool:
        rules = self._parse_rules(self.rules.get(field, []))
        return any(isinstance(r, str) and r.split(":")[0] in ("integer", "numeric") for r in rules)

    def _size(self, value: Any, field: str | None = None) -> float:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            # A numeric-typed field compares by VALUE, not length (form input is strings):
            # `integer|min:18` on "18" is 18, not len 2 — matching Laravel's getSize().
            if field is not None and _is_number(value) and self._has_numeric_rule(field):
                return float(value)
            return len(value)
        if isinstance(value, (list, dict, tuple)):
            return len(cast("Sized", value))
        return 0

    def _check(self, rule: str, value: Any, arg: str, field: str) -> bool:
        match rule:
            case "required":
                return value not in (None, "", [], {})
            case "string":
                return isinstance(value, str)
            case "integer":
                return (isinstance(value, int) and not isinstance(value, bool)) or (
                    isinstance(value, str) and value.lstrip("-").isdigit()
                )
            case "numeric":
                return (isinstance(value, (int, float)) and not isinstance(value, bool)) or (
                    isinstance(value, str) and _is_number(value)
                )
            case "boolean":
                return value in (True, False, 0, 1, "0", "1", "true", "false")
            case "email":
                return isinstance(value, str) and bool(_EMAIL.match(value))
            case "url":
                return isinstance(value, str) and value.startswith(("http://", "https://"))
            case "alpha":
                return isinstance(value, str) and value.isalpha()
            case "alpha_num":
                return isinstance(value, str) and value.isalnum()
            case "in":
                return str(value) in arg.split(",")
            case "not_in":
                return str(value) not in arg.split(",")
            case "array":
                return isinstance(value, (list, tuple))
            case "between":
                low, _, high = arg.partition(",")
                return float(low) <= self._size(value, field) <= float(high)
            case "starts_with":
                return isinstance(value, str) and value.startswith(tuple(arg.split(",")))
            case "ends_with":
                return isinstance(value, str) and value.endswith(tuple(arg.split(",")))
            case "uuid":
                return isinstance(value, str) and bool(_UUID.match(value))
            case "confirmed":
                return bool(self.data.get(f"{field}_confirmation") == value)
            case "same":
                return bool(self.data.get(arg) == value)
            case "different":
                return bool(self.data.get(arg) != value)
            case "accepted":
                return value in (True, "yes", "on", 1, "1", "true")
            case "regex":
                return isinstance(value, str) and bool(re.search(arg, value))
            case "min":
                return self._size(value, field) >= float(arg)
            case "max":
                return self._size(value, field) <= float(arg)
            case "size":
                return self._size(value, field) == float(arg)
            case "gt" | "gte" | "lt" | "lte":
                from arvel.support.helpers import data_get

                # Laravel sizes BOTH operands by the field-under-validation's rules (same `field`),
                # so `numeric|gt:other` compares values, not the other field's string length.
                this, other = self._size(value, field), self._size(data_get(self.data, arg), field)
                return {"gt": this > other, "gte": this >= other, "lt": this < other}.get(
                    rule, this <= other
                )
            case "digits":
                return str(value).isdigit() and len(str(value)) == int(arg)
            case "digits_between":
                low, _, high = arg.partition(",")
                digits = str(value)
                return digits.isdigit() and int(low) <= len(digits) <= int(high)
            case "alpha_dash":
                return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]+", value))
            case "json":
                if not isinstance(value, (str, bytes, bytearray)):
                    return False
                try:
                    json.loads(value)  # str/bytes only raises JSONDecodeError (⊂ ValueError)
                except ValueError:
                    return False
                return True
            case "ip":
                if not isinstance(value, str):
                    return False  # Laravel's ip requires a string (rejects bare ints)
                import ipaddress

                try:
                    ipaddress.ip_address(value)
                except ValueError:
                    return False
                return True
            case "date":
                return _parse_date(value) is not None
            case "date_format":
                return _parse_date(value, arg) is not None
            case "before" | "after" | "date_equals":
                from arvel.support.helpers import data_get

                this = _parse_date(value)
                other_raw = data_get(self.data, arg, arg)  # another field, or a literal date string
                other = _parse_date(other_raw if isinstance(other_raw, str) else arg)
                if this is None or other is None:
                    return False
                if rule == "before":
                    return bool(this < other)
                if rule == "after":
                    return bool(this > other)
                return bool(this == other)
            case "file":
                return hasattr(value, "filename") or hasattr(value, "read")
            case "image":
                return str(getattr(value, "content_type", "")).startswith("image/")
            case "mimes":
                filename = str(getattr(value, "filename", ""))
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                return ext in [m.strip().lower() for m in arg.split(",")]
            case "unique" | "exists":
                return True  # DB rules — validated asynchronously in passes_async; no-op here
            case _:
                if self.strict:
                    raise UnknownValidationRule(rule)
                return True  # unknown rule is a no-op (lenient default)

    def _message(self, field: str, rule: str, arg: str) -> str:
        custom = self.messages.get(f"{field}.{rule}") or self.messages.get(rule)
        if custom is not None:
            return custom.format(field=field, arg=arg)
        localized = self._localized_message(field, rule, arg)
        if localized is not None:
            return localized
        return _DEFAULT_MESSAGES.get(rule, "The {field} is invalid.").format(field=field, arg=arg)

    @staticmethod
    def _localized_message(field: str, rule: str, arg: str) -> str | None:
        """A ``validation.{rule}`` line from the bound translator (resolved for the current
        locale), or ``None`` when no app/translator is present or the key isn't translated."""
        from arvel.kernel import app, has_application

        if not (has_application() and app().bound("translator")):
            return None
        key = f"validation.{rule}"
        line: str = app("translator").get(key, {"field": field, "arg": arg})
        return line if line != key else None  # translator returns the key on a miss


__all__ = [
    "FormRequest",
    "Rule",
    "Schema",
    "UnknownValidationRule",
    "ValidationException",
    "Validator",
    "json_schema",
    "validate",
]
