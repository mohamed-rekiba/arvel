"""Item 3b — use_default_groups() merges rather than overwrites: a group customized before
serve (append_to_group / middleware_group) is preserved; only empty groups get the defaults."""

from __future__ import annotations

from typing import Any

from arvel.http import HttpKernel
from arvel.http.middleware import (
    EncryptCookies,
    ShareErrorsFromSession,
    StartSession,
    ThrottleRequests,
    ValidateCsrfToken,
)


class _Custom:
    async def handle(self, request: Any, call_next: Any) -> Any:
        return await call_next(request)


def test_defaults_fill_empty_groups() -> None:
    kernel = HttpKernel().use_default_groups()
    assert kernel.groups["web"] == [
        EncryptCookies,  # H7 — first, so every cookie below it goes through its codec
        StartSession,
        ShareErrorsFromSession,
        ValidateCsrfToken,
    ]
    assert kernel.groups["api"] == [ThrottleRequests]


def test_customized_group_is_not_overwritten() -> None:
    kernel = HttpKernel()
    kernel.middleware_group("web", [_Custom])  # app customizes web before serve
    kernel.use_default_groups()
    assert kernel.groups["web"] == [_Custom]  # preserved, not clobbered
    assert kernel.groups["api"] == [ThrottleRequests]  # api was empty → filled


def test_append_to_group_survives_defaults() -> None:
    kernel = HttpKernel()
    kernel.append_to_group("api", _Custom)
    kernel.use_default_groups()
    assert kernel.groups["api"] == [_Custom]  # defaults not appended (group non-empty)
    assert kernel.groups["web"] == [
        EncryptCookies,
        StartSession,
        ShareErrorsFromSession,
        ValidateCsrfToken,
    ]
