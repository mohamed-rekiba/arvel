"""HTTP — ValidateCsrfToken web-group middleware."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.middleware import ValidateCsrfToken
from arvel.validation import ValidationException


class FakeRequest:
    def __init__(
        self, method: str, sent_token: str | None, session_token: str | None = "tok"
    ) -> None:
        self._method = method
        self._headers = {"x-csrf-token": sent_token}
        self.session: dict[str, Any] = {"_token": session_token} if session_token else {}

    def method(self) -> str:
        return self._method

    def header(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name, default)


async def _ok(_request: Any) -> str:
    return "ok"


async def test_safe_method_skips_csrf() -> None:
    csrf = ValidateCsrfToken()
    # GET needs no token even with none present
    assert await csrf.handle(FakeRequest("GET", sent_token=None), _ok) == "ok"


async def test_matching_token_passes() -> None:
    csrf = ValidateCsrfToken()
    assert (
        await csrf.handle(FakeRequest("POST", sent_token="tok", session_token="tok"), _ok) == "ok"
    )


async def test_missing_token_rejected_419() -> None:
    csrf = ValidateCsrfToken()
    with pytest.raises(ValidationException) as exc:
        await csrf.handle(FakeRequest("POST", sent_token=None), _ok)
    assert exc.value.status == 419


async def test_mismatched_token_rejected_419() -> None:
    csrf = ValidateCsrfToken()
    with pytest.raises(ValidationException) as exc:
        await csrf.handle(FakeRequest("POST", sent_token="wrong", session_token="tok"), _ok)
    assert exc.value.status == 419
