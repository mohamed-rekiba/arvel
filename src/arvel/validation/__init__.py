"""arvel.validation — schema-first validation on **msgspec** (core; DR-0002).

``validate(data, Schema)`` coerces+validates a mapping into a typed ``msgspec.Struct``
(422 ``ValidationException`` on failure); ``json_schema(Schema)`` emits the JSON
schema Litestar feeds into OpenAPI (G4). ``FormRequest`` is a Struct base with
``parse``/``authorize``. msgspec is core. Grounded in knowledge/port/10-validation.md.
"""

from __future__ import annotations

import json
import re
from enum import Enum as _PyEnum
from typing import TYPE_CHECKING, Any, Self, cast

import msgspec

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sized


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

    **The rules() bridge (spec 12 §3).** msgspec stays the type/shape layer — annotations are
    the whole story for most requests. When a request needs *semantic* checks msgspec can't
    express (cross-field, conditional — the ``rules()``), override ``rules()`` (a normal
    rule ``Validator`` ruleset) and optionally ``messages()`` / ``attributes()`` / a
    ``with_validator()`` hook to register ``sometimes()``/``after()``. Those run against the
    *decoded* payload right after msgspec's structural pass succeeds; a rule failure raises the
    same ``ValidationException`` (same 422 shape) msgspec itself would raise. Two disjoint
    validators, one error bag — not a dual engine: msgspec still owns types, ``rules()`` only
    ever adds semantics on top.
    """

    @classmethod
    def prepare_for_validation(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Hook: normalize/augment the raw input before validation (default: unchanged)."""
        return data

    def passed_validation(self) -> None:
        """Hook: run after a successful parse — derive/clean fields (default: no-op)."""

    @classmethod
    def rules(cls) -> dict[str, str | list[Any]]:
        """Optional hook: extra rule-engine checks, run against the
        decoded payload after msgspec's structural pass. Default: none."""
        return {}

    @classmethod
    def messages(cls) -> dict[str, str]:
        """Optional hook: message overrides for ``rules()``."""
        return {}

    @classmethod
    def attributes(cls) -> dict[str, str]:
        """Optional hook: friendly field-name overrides used in ``rules()`` messages."""
        return {}

    @classmethod
    def with_validator(cls, validator: Validator) -> None:
        """Optional hook: register ``sometimes()``/``after()`` on the rule ``Validator`` before
        it runs. Default: no-op."""

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> Self:
        prepared = cls.prepare_for_validation(dict(data))
        instance = validate(prepared, cls)
        extra_rules = cls.rules()
        if extra_rules:
            validator = Validator(
                prepared, extra_rules, cls.messages(), attributes=cls.attributes()
            )
            cls.with_validator(validator)
            if validator.fails():
                raise ValidationException(validator.errors())
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


_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+")
_EMAIL_DOMAIN = re.compile(r"(?!-)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_URL_DEFAULT_SCHEMES = ("http", "https")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _check_email(value: Any) -> bool:
    """RFC-lite (spec A7): local@domain+TLD, no leading/trailing/consecutive dots in either
    part, the length caps (local <=64, domain <=255). A format check — no DNS/mailbox
    probe (that's `active_url`'s footgun, deliberately not ported; see `_check_url`)."""
    if not isinstance(value, str) or "@" not in value:
        return False
    local, _, domain = value.rpartition("@")
    if not local or not domain or len(local) > 64 or len(domain) > 255:
        return False
    if ".." in local or ".." in domain or local[0] == "." or local[-1] == ".":
        return False
    return bool(_EMAIL_LOCAL.fullmatch(local)) and bool(_EMAIL_DOMAIN.fullmatch(domain))


def _check_url(value: Any, arg: str) -> bool:
    """Structural parse (spec A7): scheme in the allowed set (default http/https, or the
    `url:scheme1,scheme2` arg), a non-empty host, no whitespace. Deliberately NOT `active_url`
    — a DNS lookup in a validation layer is a footgun (network call on every request); divergence
    is intentional and documented in docs/validation.md."""
    if not isinstance(value, str) or any(ch.isspace() for ch in value):
        return False
    from urllib.parse import urlsplit

    allowed = tuple(s.strip() for s in arg.split(",")) if arg else _URL_DEFAULT_SCHEMES
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in allowed and bool(parts.netloc)


def _upload_bytes(value: Any) -> bytes | None:
    """Best-effort *synchronous* byte read for `dimensions` — the rule engine is sync, so an
    async `UploadedFile.read()` can't be awaited here. Handles raw `bytes`, litestar's
    `UploadFile.file` (a sync `SpooledTemporaryFile`), or any file-like with a sync `read()`
    (e.g. `io.BytesIO`). ponytail: no async bridge — read the upload yourself first
    (`io.BytesIO(await file.read())`) for the real async-upload path; see docs."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    file_obj = getattr(value, "file", None)
    if file_obj is not None and hasattr(file_obj, "read"):
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        return cast("bytes", file_obj.read())
    reader = getattr(value, "read", None)
    if callable(reader):
        result = reader()
        if isinstance(result, (bytes, bytearray)):
            return bytes(result)
    return None


def _parse_ratio(raw: str) -> float:
    if "/" in raw:
        num, _, den = raw.partition("/")
        return float(num) / float(den)
    return float(raw)


def _check_dimensions(value: Any, arg: str) -> bool:
    """`dimensions:min_width=…,ratio=…` — reads real pixel data via Pillow (lazy import; the
    `image` extra, already installed for `arvel.media`). Missing the extra is an honest failure
    (`MissingExtraError`), not a silent pass."""
    from arvel.support.manager import MissingExtraError

    try:
        from PIL import Image  # import-guard only; funneled through Any below
    except ImportError as exc:
        raise MissingExtraError("image", "image") from exc
    raw = _upload_bytes(value)
    if raw is None:
        return False
    import io

    pil_image: Any = Image  # Pillow's typing is incomplete for our use — funnel it through Any
    try:
        with pil_image.open(io.BytesIO(raw)) as img:
            width, height = cast("tuple[int, int]", img.size)
    except OSError, ValueError:
        return False
    constraints = dict(pair.split("=", 1) for pair in arg.split(",") if "=" in pair)
    if "width" in constraints and width != int(constraints["width"]):
        return False
    if "height" in constraints and height != int(constraints["height"]):
        return False
    if "min_width" in constraints and width < int(constraints["min_width"]):
        return False
    if "min_height" in constraints and height < int(constraints["min_height"]):
        return False
    if "max_width" in constraints and width > int(constraints["max_width"]):
        return False
    if "max_height" in constraints and height > int(constraints["max_height"]):
        return False
    return not (
        "ratio" in constraints and abs(width / height - _parse_ratio(constraints["ratio"])) >= 1e-2
    )


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
    # New story-12 rules deliberately have NO entry here — `_DEFAULT_MESSAGES` is guarded 1:1
    # against the shipped `localization/lang/en/validation.json` (outside this story's scope:
    # src/arvel/validation/, tests/, docs/validation.md only), so they fall back to the generic
    # "The {field} is invalid." below rather than drift the two out of sync.
}


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _ascii_digits(s: str) -> bool:
    # narrower than str.isdigit(), which also accepts superscripts/Arabic-Indic/etc.
    return s.isascii() and s.isdigit()


# implicit rules run even when the value is absent/None — `nullable` must NOT suppress them.
_IMPLICIT_RULES = frozenset(
    {
        "required",
        "required_if",
        "required_unless",
        "required_with",
        "required_with_all",
        "required_without",
        "required_without_all",
        "present",
        "filled",
        "accepted",
        "accepted_if",
        "declined",
        "declined_if",
        "missing",
        "missing_if",
        "missing_unless",
        "missing_with",
        "missing_with_all",
    }
)


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
    segment is an integer index — so ``items.0.price`` rebuilds ``{"items": [{"price":...}]}``.

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
    arvel is Python, so date_format uses Python codes, not the PHP codes), only that format is
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

    def passes(self, attribute: str, value: Any) -> bool:
        raise NotImplementedError(f"{type(self).__name__} must implement passes()")


class Enum(Rule):
    """Rule object: value-in-enum membership. No string
    form — the enum class *is* the closed set, so it's typed rather than stringly-parsed:
    ``{"status": [Enum(Status)]}``. A plain ``Rule`` subclass, so it runs wherever the ruleset
    runs — sync ``passes()`` and async ``passes_async()`` alike."""

    def __init__(self, enum_cls: type[_PyEnum]) -> None:
        self._enum_cls = enum_cls
        self.message = f"The :attribute is not a valid {enum_cls.__name__}."

    def passes(self, attribute: str, value: Any) -> bool:
        try:
            self._enum_cls(value)
        except ValueError:
            return False
        return True


class Validator:
    """Rule-based validation.

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
        stop_on_first_failure: bool = False,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self.data = dict(data)
        self.rules: dict[str, str | list[Any]] = dict(rules)
        self.messages = dict(messages or {})
        self.attribute_names = dict(attributes or {})
        self._errors: dict[str, list[str]] = {}
        #: fields dropped from validated() by `exclude`/`exclude_if`/`exclude_unless`
        self._excluded: set[str] = set()
        #: post-pass hooks registered via `after()`
        self._after: list[Callable[[Validator], None]] = []
        self._connection = connection  # for async DB rules (unique/exists)
        #: when True, an unrecognized rule name raises ``UnknownValidationRule`` instead of no-op'ing
        self.strict = strict
        #: when True, the WHOLE pass stops at the first field to fail
        self.stop_on_first_failure = stop_on_first_failure

    def _parse_rules(self, ruleset: str | list[Any]) -> list[Any]:
        return (
            [r.strip() for r in ruleset.split("|")] if isinstance(ruleset, str) else list(ruleset)
        )

    def sometimes(
        self, field: str, rules: str | list[Any], condition: Callable[[Mapping[str, Any]], bool]
    ) -> Self:
        """Add ``rules`` to ``field`` only when ``condition(self.data)`` is true (``Validator::sometimes``) — for conditions too broad for a single-field rule string."""
        if condition(self.data):
            existing = self.rules.get(field)
            merged = (self._parse_rules(existing) if existing else []) + self._parse_rules(rules)
            self.rules[field] = merged
        return self

    def after(self, callback: Callable[[Validator], None]) -> Self:
        """Register a post-pass hook — runs once every field's rules have
        been checked; add errors via ``add_error()``."""
        self._after.append(callback)
        return self

    def add_error(self, field: str, message: str) -> None:
        """Append a validation error for ``field`` — the way an ``after()`` hook reports a
        failure it discovered (a cross-field/business check no single rule expresses)."""
        self._errors.setdefault(field, []).append(message)

    def passes(self) -> bool:
        from arvel.support.helpers import data_get

        self._errors = {}
        self._excluded = set()
        for field, ruleset in self.rules.items():
            rules = self._parse_rules(ruleset)
            if "*" in field:  # nested array rule (items.*.price)
                self._validate_wildcard(field, rules)
                if self.stop_on_first_failure and self._errors:
                    break
                continue
            if "sometimes" in rules and field not in self.data:
                continue  # only validate when the field is present
            # data_get resolves dot-paths into nested dicts, not just flat keys
            value = data_get(self.data, field)
            # `nullable` suppresses only NON-implicit rules on a null value; required-family and
            # other implicit rules still run (and fail) so `required|nullable` isn't a no-op.
            nullable_none = value is None and "nullable" in rules
            bail = "bail" in rules  # stop THIS field's rules at its first failure
            for rule in rules:
                if isinstance(rule, Rule):  # custom rule object — sync predicate (non-implicit)
                    if nullable_none:
                        continue
                    if not rule.passes(field, value):
                        self._errors.setdefault(field, []).append(
                            rule.message.replace(":attribute", field)
                        )
                        if bail:
                            break
                    continue
                if not isinstance(rule, str):
                    continue
                if rule in ("nullable", "sometimes", "bail"):
                    continue
                name, _, arg = rule.partition(":")
                if nullable_none and name not in _IMPLICIT_RULES:
                    continue
                if not self._check(name, value, arg, field):
                    self._errors.setdefault(field, []).append(self._message(field, name, arg))
                    if bail:
                        break
            if self.stop_on_first_failure and self._errors:
                break
        for hook in self._after:
            hook(self)
        return not self._errors

    def _validate_wildcard(self, field: str, rules: list[Any]) -> None:
        """Apply rules to each element of a ``a.*.b`` path, keying errors by the resolved index.
        ``distinct`` is checked once across all siblings (it needs the whole array, not a single
        element) before the per-element loop runs the rest."""
        from arvel.support.helpers import data_get

        values = data_get(self.data, field)
        if not isinstance(values, list):
            return
        values_list = cast("list[Any]", values)
        if "distinct" in rules:
            seen: list[Any] = []
            for index, sibling in enumerate(values_list):
                key = field.replace("*", str(index), 1)
                if sibling in seen:
                    self._errors.setdefault(key, []).append(self._message(key, "distinct", ""))
                else:
                    seen.append(sibling)
        bail = "bail" in rules
        for index, value in enumerate(values_list):
            key = field.replace("*", str(index), 1)
            for rule in rules:
                if isinstance(rule, Rule):  # custom rule object — sync predicate
                    if not rule.passes(key, value):
                        self._errors.setdefault(key, []).append(
                            rule.message.replace(":attribute", key)
                        )
                        if bail:
                            break
                    continue
                if not isinstance(rule, str):
                    continue
                if rule in ("nullable", "sometimes", "bail", "distinct"):
                    continue
                name, _, arg = rule.partition(":")
                # a sibling reference in the arg (`required_if:items.*.active,yes`) resolves
                # against THIS element's index, not every element's.
                arg = arg.replace("*", str(index))
                if not self._check(name, value, arg, key):
                    self._errors.setdefault(key, []).append(self._message(key, name, arg))
                    if bail:
                        break

    def fails(self) -> bool:
        return not self.passes()

    async def passes_async(self) -> bool:
        """Run the synchronous rules (incl. custom ``Rule``/``Enum`` objects), then the async DB
        rules (``unique``/``exists``) that can't run on the sync path."""
        from arvel.support.helpers import data_get

        self.passes()  # sync rules, custom Rule objects included — not re-run below
        for field, ruleset in self.rules.items():
            rules = self._parse_rules(ruleset)
            if "sometimes" in rules and field not in self.data:
                continue
            value = data_get(self.data, field)
            if value is None and "nullable" in rules:
                continue
            bail = "bail" in rules
            for rule in rules:
                if not isinstance(rule, str):
                    continue
                name, _, arg = rule.partition(":")
                if name in ("unique", "exists") and not await self._check_db(
                    name, value, arg, field
                ):
                    self._errors.setdefault(field, []).append(self._message(field, name, arg))
                    if bail:
                        break
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
        """The validated subset of the input, with nesting preserved.

        Each rule's field is resolved by dot-path — so a ``user.email`` rule contributes the nested
        value it validated — and the result rebuilds that nesting (``{"user": {"email":...}}``)
        rather than a flat ``"user.email"`` key. Wildcard rules (``items.*.price``) put each
        validated leaf back in its array position. A field absent from the input is omitted (so an
        absent ``sometimes`` field never appears); a present field whose value is ``None`` is kept.
        """
        from arvel.support.helpers import Arr, data_get

        result: dict[str, Any] = {}
        for field in self.rules:
            if field in self._excluded:  # `exclude`/`exclude_if`/`exclude_unless` (spec 12 §2)
                continue
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
            # `integer|min:18` on "18" is 18, not len 2 — matching the getSize().
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
                    isinstance(value, str) and _ascii_digits(value.lstrip("-"))
                )
            case "numeric":
                return (isinstance(value, (int, float)) and not isinstance(value, bool)) or (
                    isinstance(value, str) and _is_number(value)
                )
            case "boolean":
                return value in (True, False, 0, 1, "0", "1")
            case "email":
                return _check_email(value)
            case "url":
                return _check_url(value, arg)
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
                from arvel.support.helpers import data_get

                return bool(data_get(self.data, f"{field}_confirmation") == value)
            case "same":
                from arvel.support.helpers import data_get

                return bool(data_get(self.data, arg) == value)
            case "different":
                from arvel.support.helpers import data_get

                return bool(data_get(self.data, arg) != value)
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

                # sizes BOTH operands by the field-under-validation's rules (same `field`),
                # so `numeric|gt:other` compares values, not the other field's string length.
                this, other = self._size(value, field), self._size(data_get(self.data, arg), field)
                return {"gt": this > other, "gte": this >= other, "lt": this < other}.get(
                    rule, this <= other
                )
            case "digits":
                return _ascii_digits(str(value)) and len(str(value)) == int(arg)
            case "digits_between":
                low, _, high = arg.partition(",")
                digits = str(value)
                return _ascii_digits(digits) and int(low) <= len(digits) <= int(high)
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
                    return False  # the ip requires a string (rejects bare ints)
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
            case "dimensions":
                return _check_dimensions(value, arg)
            case "exclude":
                self._excluded.add(field)
                return True
            case "exclude_if":
                from arvel.support.helpers import data_get

                other_field, _, val = arg.partition(",")
                if str(data_get(self.data, other_field)) == val:
                    self._excluded.add(field)
                return True
            case "exclude_unless":
                from arvel.support.helpers import data_get

                other_field, _, val = arg.partition(",")
                if str(data_get(self.data, other_field)) != val:
                    self._excluded.add(field)
                return True
            case "unique" | "exists":
                return True  # DB rules — validated asynchronously in passes_async; no-op here
            case _:
                from arvel.validation import rules as _rules

                extra = _rules.check(self, rule, value, arg, field)
                if extra is not None:
                    return extra
                if self.strict:
                    raise UnknownValidationRule(rule)
                return True  # unknown rule is a no-op (lenient default)

    def _message(self, field: str, rule: str, arg: str) -> str:
        # `attributes()` (spec 12 §3) swaps in a friendly name for display only — error keys and
        # message-override lookups still key off the real `field`.
        display = self.attribute_names.get(field, field)
        custom = self.messages.get(f"{field}.{rule}") or self.messages.get(rule)
        if custom is not None:
            return custom.format(field=display, arg=arg)
        localized = self._localized_message(field, rule, arg)
        if localized is not None:
            return localized
        return _DEFAULT_MESSAGES.get(rule, "The {field} is invalid.").format(field=display, arg=arg)

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
    "Enum",
    "FormRequest",
    "Rule",
    "Schema",
    "UnknownValidationRule",
    "ValidationException",
    "Validator",
    "json_schema",
    "validate",
]
