"""HTTP/L10n (doc 21) — LocaleMiddleware prefers the user's locale over Accept-Language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arvel.auth import current_user
from arvel.http.middleware import LocaleMiddleware
from arvel.localization import current_locale


@dataclass
class Req:
    headers: dict[str, str]

    def header(self, name: str) -> str | None:
        return self.headers.get(name)


@dataclass
class User:
    locale: str | None = None


async def _capture(_req: Any) -> str:
    return current_locale.get()


async def test_user_pref_wins_over_header() -> None:
    token = current_user.set(User(locale="fr"))
    try:
        result = await LocaleMiddleware().handle(Req({"accept-language": "de-DE,de"}), _capture)
        assert result == "fr"
    finally:
        current_user.reset(token)


async def test_falls_back_to_header_when_user_has_no_locale() -> None:
    token = current_user.set(User(locale=None))
    try:
        result = await LocaleMiddleware().handle(Req({"accept-language": "es-ES,es"}), _capture)
        assert result == "es"
    finally:
        current_user.reset(token)


async def test_header_used_when_no_user() -> None:
    result = await LocaleMiddleware().handle(Req({"accept-language": "ja"}), _capture)
    assert result == "ja"


async def test_passthrough_when_nothing_resolves() -> None:
    before = current_locale.get()
    result = await LocaleMiddleware().handle(Req({}), _capture)
    assert result == before  # locale unchanged


async def test_user_pref_applies_under_the_real_wiring_order() -> None:
    """In the shipped wiring LocaleMiddleware (early global) runs BEFORE AuthenticateMiddleware
    (app-registered global), and the kernel resets current_user at dispatch — so at Locale-time
    there is never a user and the documented user-pref precedence was dead code. Authenticate now
    applies the resolved user's preferred locale itself, so the promise holds in the real order."""
    from arvel.http.middleware import AuthenticateMiddleware
    from arvel.kernel import set_application
    from arvel.kernel.application import Application

    app = Application()
    app.instance("user_resolver", lambda request: User(locale="fr"))
    set_application(app)
    try:
        authenticate = AuthenticateMiddleware()

        async def auth_then_capture(request: Any) -> str:
            return await authenticate.handle(request, _capture)

        # Locale first (header says de), then Auth resolves the fr-preferring user — as wired
        result = await LocaleMiddleware().handle(
            Req({"accept-language": "de-DE,de"}), auth_then_capture
        )
        assert result == "fr"
    finally:
        set_application(None)


async def test_auth_without_a_user_pref_keeps_the_header_locale() -> None:
    from arvel.http.middleware import AuthenticateMiddleware
    from arvel.kernel import set_application
    from arvel.kernel.application import Application

    app = Application()
    app.instance("user_resolver", lambda request: User(locale=None))
    set_application(app)
    try:
        authenticate = AuthenticateMiddleware()

        async def auth_then_capture(request: Any) -> str:
            return await authenticate.handle(request, _capture)

        result = await LocaleMiddleware().handle(
            Req({"accept-language": "es-ES,es"}), auth_then_capture
        )
        assert result == "es"
    finally:
        set_application(None)


def test_user_pref_survives_the_served_kernel_stack() -> None:
    """Full-wiring regression guard: the precedence must hold through the BUILT kernel
    (use_default_global + an app-registered Authenticate global, production order) — a
    registration-order regression only shows up here, not in hand-composed chains."""
    from litestar.testing import TestClient

    from arvel.http import HttpKernel
    from arvel.http.middleware import AuthenticateMiddleware
    from arvel.kernel import set_application
    from arvel.kernel.application import Application
    from arvel.routing import Router

    app = Application()
    app.instance("user_resolver", lambda request: User(locale="fr"))
    set_application(app)
    try:

        async def which_locale(request: Any) -> dict[str, str]:
            return {"locale": current_locale.get() or ""}

        router = Router()
        router.get("/which-locale", which_locale)
        kernel = HttpKernel()
        kernel.use_default_global()  # Locale lands in the early defaults
        kernel.global_middleware.append(AuthenticateMiddleware)  # after it, as apps wire it
        router.apply_to(kernel)
        with TestClient(kernel.build()) as client:
            got = client.get("/which-locale", headers={"accept-language": "de-DE,de"})
            assert got.json()["locale"] == "fr"  # user pref beats the header, full stack
    finally:
        set_application(None)


# --- an explicit switch outranks the stored preference ---------------------
@dataclass
class SwitchReq:
    headers: dict[str, str]
    q: dict[str, str] | None = None
    cookies: dict[str, str] | None = None

    def header(self, name: str) -> str | None:
        return self.headers.get(name)

    def query(self, key: str, default: Any = None) -> Any:
        return (self.q or {}).get(key, default)

    def cookie(self, name: str, default: Any = None) -> Any:
        return (self.cookies or {}).get(name, default)


async def test_query_switch_beats_user_pref() -> None:
    token = current_user.set(User(locale="fr"))
    try:
        req = SwitchReq({"accept-language": "de"}, q={"lang": "es"})
        assert await LocaleMiddleware().handle(req, _capture) == "es"  # switch wins over fr
    finally:
        current_user.reset(token)


async def test_locale_cookie_switch_beats_user_pref() -> None:
    token = current_user.set(User(locale="fr"))
    try:
        req = SwitchReq({"accept-language": "de"}, cookies={"locale": "it"})
        assert await LocaleMiddleware().handle(req, _capture) == "it"
    finally:
        current_user.reset(token)


async def test_switch_normalizes_region_subtag() -> None:
    req = SwitchReq({}, q={"locale": "pt-BR"})
    assert await LocaleMiddleware().handle(req, _capture) == "pt"


async def test_malicious_switch_value_is_ignored() -> None:
    # a path-traversal attempt must not become the locale (it feeds translation-file lookups)
    token = current_user.set(User(locale="fr"))
    try:
        req = SwitchReq({"accept-language": "de"}, q={"lang": "../../etc/passwd"})
        assert await LocaleMiddleware().handle(req, _capture) == "fr"  # falls back to user pref
    finally:
        current_user.reset(token)


async def test_switch_beats_stored_pref_under_real_wiring() -> None:
    from arvel.http.middleware import AuthenticateMiddleware
    from arvel.kernel import set_application
    from arvel.kernel.application import Application

    app = Application()
    app.instance("user_resolver", lambda request: User(locale="fr"))
    set_application(app)
    try:
        authenticate = AuthenticateMiddleware()

        async def auth_then_capture(request: Any) -> str:
            return await authenticate.handle(request, _capture)

        req = SwitchReq({"accept-language": "de"}, cookies={"locale": "es"})
        # user resolves to fr, but the explicit es switch must win end-to-end
        assert await LocaleMiddleware().handle(req, auth_then_capture) == "es"
    finally:
        set_application(None)


async def test_invalid_query_does_not_shadow_a_valid_cookie() -> None:
    # a present-but-malformed higher-precedence ?lang= must not block a valid lower-precedence cookie
    req = SwitchReq({"accept-language": "de"}, q={"lang": "../../etc"}, cookies={"locale": "es"})
    assert await LocaleMiddleware().handle(req, _capture) == "es"
