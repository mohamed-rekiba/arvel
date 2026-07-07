"""HTTP — ValidateCsrfToken web-group middleware."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.exceptions import HttpException
from arvel.http.middleware import ValidateCsrfToken


class FakeRequest:
    def __init__(
        self,
        method: str,
        sent_token: str | None,
        session_token: str | None = "tok",
        *,
        origin: str | None = None,
        referer: str | None = None,
        host: str | None = "app.test",
        path: str = "submit",
    ) -> None:
        self._method = method
        self._headers = {"x-csrf-token": sent_token, "origin": origin, "referer": referer}
        self._host = host
        self._path = path
        self.session: dict[str, Any] = {"_token": session_token} if session_token else {}

    def method(self) -> str:
        return self._method

    def header(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name) or default

    def host(self) -> str | None:
        return self._host

    def is_(self, pattern: str) -> bool:
        import fnmatch

        return fnmatch.fnmatch(self._path, pattern)


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
    with pytest.raises(HttpException) as exc:
        await csrf.handle(FakeRequest("POST", sent_token=None), _ok)
    assert exc.value.status == 419


async def test_mismatched_token_rejected_419() -> None:
    csrf = ValidateCsrfToken()
    with pytest.raises(HttpException) as exc:
        await csrf.handle(FakeRequest("POST", sent_token="wrong", session_token="tok"), _ok)
    assert exc.value.status == 419


# --- origin-aware verification: provenance is a gate on top of the token, never instead ----


async def test_same_origin_with_token_passes() -> None:
    csrf = ValidateCsrfToken()
    req = FakeRequest("POST", sent_token="tok", origin="https://app.test")
    assert await csrf.handle(req, _ok) == "ok"


async def test_cross_origin_rejected_even_with_valid_token() -> None:
    csrf = ValidateCsrfToken()
    req = FakeRequest("POST", sent_token="tok", origin="https://evil.test")
    with pytest.raises(HttpException) as exc:
        await csrf.handle(req, _ok)
    assert exc.value.status == 419


async def test_null_origin_rejected() -> None:
    csrf = ValidateCsrfToken()
    req = FakeRequest("POST", sent_token="tok", origin="null")
    with pytest.raises(HttpException) as exc:
        await csrf.handle(req, _ok)
    assert exc.value.status == 419


async def test_no_origin_falls_back_to_referer() -> None:
    csrf = ValidateCsrfToken()
    cross = FakeRequest("POST", sent_token="tok", referer="https://evil.test/form")
    with pytest.raises(HttpException):
        await csrf.handle(cross, _ok)
    same = FakeRequest("POST", sent_token="tok", referer="https://app.test/form")
    assert await csrf.handle(same, _ok) == "ok"


async def test_no_origin_no_referer_stays_token_only() -> None:
    # curl/API clients send neither header; the token remains the only gate
    csrf = ValidateCsrfToken()
    assert await csrf.handle(FakeRequest("POST", sent_token="tok"), _ok) == "ok"


async def test_trusted_origins_full_and_bare_host() -> None:
    csrf = ValidateCsrfToken()
    csrf._trusted = ["https://partner.test:8443", "cdn.test"]
    full = FakeRequest("POST", sent_token="tok", origin="https://partner.test:8443")
    assert await csrf.handle(full, _ok) == "ok"
    bare = FakeRequest("POST", sent_token="tok", origin="http://cdn.test:9000")
    assert await csrf.handle(bare, _ok) == "ok"
    other_port = FakeRequest("POST", sent_token="tok", origin="https://partner.test:9999")
    with pytest.raises(HttpException):
        await csrf.handle(other_port, _ok)


async def test_excepted_path_bypasses_origin_and_token() -> None:
    class Hooky(ValidateCsrfToken):
        except_ = ["webhooks/*"]

    req = FakeRequest("POST", sent_token=None, origin="https://evil.test", path="webhooks/pay")
    assert await Hooky().handle(req, _ok) == "ok"


async def test_get_is_never_origin_checked() -> None:
    csrf = ValidateCsrfToken()
    req = FakeRequest("GET", sent_token=None, origin="https://evil.test")
    assert await csrf.handle(req, _ok) == "ok"


async def test_unparseable_referer_fails_closed() -> None:
    # a client that asserts provenance it can't prove is rejected, not waved through
    csrf = ValidateCsrfToken()
    scheme_relative = FakeRequest("POST", sent_token="tok", referer="//evil.test/form")
    with pytest.raises(HttpException):
        await csrf.handle(scheme_relative, _ok)
    garbage = FakeRequest("POST", sent_token="tok", referer=":not a url")
    with pytest.raises(HttpException):
        await csrf.handle(garbage, _ok)


async def test_origin_without_hostname_fails_closed() -> None:
    csrf = ValidateCsrfToken()
    req = FakeRequest("POST", sent_token="tok", origin="https://")
    with pytest.raises(HttpException):
        await csrf.handle(req, _ok)


async def test_full_origin_trusted_entry_matches_case_insensitively() -> None:
    csrf = ValidateCsrfToken()
    csrf._trusted = ["https://Partner.Test:8443"]
    req = FakeRequest("POST", sent_token="tok", origin="https://partner.test:8443")
    assert await csrf.handle(req, _ok) == "ok"
