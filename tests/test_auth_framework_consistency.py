"""Auth (L1c) — framework-capability consistency: Hash + Http resolved from the container.

(The Log-facade path is covered in test_auth_impersonation.py via Log.swap.)
"""

from __future__ import annotations

from typing import Any

from arvel.auth.oauth import fetch_userinfo
from arvel.kernel.globals import set_application
from arvel.security import Hasher, resolve_hasher


class _FakeApp:
    def __init__(self, bindings: dict[str, Any]) -> None:
        self._b = bindings

    def make(self, key: str) -> Any:
        return self._b[key]

    def bound(self, key: str) -> bool:
        return key in self._b


# --- V2: hasher resolves from the container ----------------------------------


def test_resolve_hasher_falls_back_without_app() -> None:
    set_application(None)
    assert isinstance(resolve_hasher(), Hasher)


def test_resolve_hasher_uses_container_when_bound() -> None:
    sentinel = Hasher()  # stands in for an app-configured hasher
    set_application(_FakeApp({"hash": sentinel}))
    try:
        assert resolve_hasher() is sentinel  # the bound instance, not a fresh Hasher()
    finally:
        set_application(None)


# --- V3: userinfo uses the framework http client -----------------------------


class _FakeResp:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"sub": "x"}


class _FakeHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    async def get(self, url: str, headers: dict[str, str] | None = None) -> _FakeResp:
        self.calls.append((url, headers))
        return _FakeResp()


async def test_fetch_userinfo_uses_framework_http_when_bound() -> None:
    http = _FakeHttp()
    set_application(_FakeApp({"http": http}))
    try:
        info = await fetch_userinfo("tok", "https://idp.test/userinfo")  # no client injected
    finally:
        set_application(None)
    assert info == {"sub": "x"}
    assert http.calls and http.calls[0][1] == {
        "Authorization": "Bearer tok"
    }  # framework client used
