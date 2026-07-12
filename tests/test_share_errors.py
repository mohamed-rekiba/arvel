"""ShareErrorsFromSession — flashed validation errors become the `errors` view global on every
request, and it's wired into the web group."""

from __future__ import annotations

from typing import Any

from arvel.http import HttpKernel
from arvel.http.flash import FlashBag
from arvel.http.middleware import ShareErrorsFromSession, StartSession
from arvel.kernel.application import Application


class _ViewSpy:
    def __init__(self) -> None:
        self.shared: dict[str, Any] = {}

    def share_request(self, **values: Any) -> None:
        self.shared.update(values)


class _Req:
    def __init__(self, session: dict[str, Any] | None) -> None:
        self.session = session


async def _passthrough(request: Any) -> str:
    return "ok"


async def test_shares_session_errors_with_the_view() -> None:
    app = Application.configure().create()
    view = _ViewSpy()
    app.instance("view", view)
    session: dict[str, Any] = {}
    FlashBag(session).flash_errors({"email": ["The email is invalid."]})

    result = await ShareErrorsFromSession().handle(_Req(session), _passthrough)

    assert result == "ok"
    assert view.shared["errors"] == {"email": ["The email is invalid."]}


async def test_shares_empty_errors_when_session_has_none() -> None:
    app = Application.configure().create()
    view = _ViewSpy()
    app.instance("view", view)

    await ShareErrorsFromSession().handle(_Req({}), _passthrough)

    assert view.shared["errors"] == {}


async def test_noop_without_session_or_view() -> None:
    app = Application.configure().create()  # no "view" bound
    view = _ViewSpy()
    # no session on the request, view bound: still a no-op (guard on session dict)
    app.instance("view", view)
    await ShareErrorsFromSession().handle(_Req(None), _passthrough)
    assert view.shared == {}


def test_wired_into_web_group_after_start_session() -> None:
    web = HttpKernel().use_default_groups().groups["web"]
    assert web.index(ShareErrorsFromSession) == web.index(StartSession) + 1
