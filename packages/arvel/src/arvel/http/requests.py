"""``FormRequest[T]`` — Pydantic-validated request input with an ``authorize()`` hook."""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar, get_args, get_origin

from pydantic import BaseModel

from arvel.http.exceptions import ValidationException
from arvel.validation import Validator

T = TypeVar("T", bound=BaseModel)


class FormRequest(Generic[T]):
    """Holds a validated payload + per-request authorization decision.

    Subclasses parameterize the payload model:

        class StoreUserRequest(FormRequest[StoreUserPayload]):
            async def authorize(self, request: Any) -> bool:
                return request.state.user is not None

    The Arvel routing layer rewrites the handler signature so FastAPI parses the
    body as ``StoreUserPayload``, then constructs ``StoreUserRequest(payload)`` and
    awaits ``authorize(request)`` before the handler runs.
    """

    _payload_type: ClassVar[type[BaseModel] | None] = None

    def __init__(self, payload: T) -> None:
        self._payload: T = payload

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Walk __orig_bases__ to find FormRequest[X] and capture X.
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is None:
                continue
            args = get_args(base)
            if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                cls._payload_type = args[0]
                return
        # Allow subclasses-of-subclasses to inherit the type.
        for parent in cls.__mro__[1:]:
            ptype = getattr(parent, "_payload_type", None)
            if isinstance(ptype, type) and issubclass(ptype, BaseModel):
                cls._payload_type = ptype
                return

    def validated(self) -> T:
        return self._payload

    def rules(self) -> dict[str, str | list[str]]:
        """Return Laravel-style rules applied after Pydantic parsing."""
        return {}

    def messages(self) -> dict[str, str]:
        """Custom messages keyed as ``field.rule`` (e.g. ``email.unique``)."""
        return {}

    def attributes(self) -> dict[str, str]:
        """Human-readable field names substituted into error messages."""
        return {}

    async def validate_rules(self, request: Any) -> None:
        data = self._payload.model_dump(mode="python")
        validator = Validator(
            data,
            request=request,
            messages=self.messages(),
            attributes=self.attributes(),
        )
        self.with_validator(validator)
        details = await validator.validate(self.rules())
        if details:
            raise ValidationException("Validation failed.", details=details)

    def with_validator(self, validator: Validator) -> None:
        """Register conditional rules on ``validator`` (e.g. ``Rule.sometimes``)."""

    async def authorize(self, request: Any) -> bool:  # noqa: ARG002
        # Deny by default — OWASP A01. Subclasses must explicitly return True.
        return False


__all__ = ["FormRequest"]
