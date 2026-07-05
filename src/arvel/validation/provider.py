"""ValidationServiceProvider — binds the ``validator`` factory (root of the Validator facade)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from arvel.kernel.service_provider import ServiceProvider
from arvel.validation import Validator

if TYPE_CHECKING:
    from arvel.contracts import Container


class ValidatorFactory:
    """Root for the ``Validator`` facade — ``Validator.make(data, rules)`` (
    ``Validator::make``) constructs a rule-based :class:`~arvel.validation.Validator`."""

    def make(
        self,
        data: Mapping[str, Any],
        rules: Mapping[str, str | list[Any]],
        messages: Mapping[str, str] | None = None,
        connection: Any = None,
        *,
        strict: bool = False,
    ) -> Validator:
        return Validator(data, rules, messages, connection, strict=strict)


class ValidationServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_validator(_app: Container) -> ValidatorFactory:
            return ValidatorFactory()

        self.app.singleton("validator", make_validator)

    def boot(self) -> None:
        """No-op."""
