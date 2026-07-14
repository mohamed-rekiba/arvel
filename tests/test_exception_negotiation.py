"""HTTP/Validation (doc 10/04) — content-negotiated ValidationException rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from arvel.http.exceptions import render_exception
from arvel.validation import ValidationException


@dataclass
class Req:
    _headers: dict[str, str] = field(default_factory=dict)
    session: dict[str, Any] | None = None

    @property
    def headers(self) -> dict[str, str]:
        return self._headers


def _exc() -> ValidationException:
    return ValidationException({"email": ["required"]})


def test_json_client_gets_422_body() -> None:
    r = render_exception(Req({"accept": "application/json"}), _exc())
    assert r.status_code == 422
    assert r.content == {"message": "Unprocessable Entity", "errors": {"email": ["required"]}}
    assert r.media_type == "application/json"


def test_default_accept_is_json() -> None:
    assert render_exception(Req({}), _exc()).status_code == 422


def test_inertia_takes_json_path_even_with_html_accept() -> None:
    r = render_exception(Req({"accept": "text/html", "x-inertia": "true"}), _exc())
    assert r.status_code == 422
    assert r.media_type == "application/json"


def test_web_redirects_back_and_flashes_errors() -> None:
    session: dict[str, Any] = {}
    req = Req({"accept": "text/html", "referer": "/signup"}, session=session)
    r = render_exception(req, _exc())
    assert r.status_code == 302
    assert r.headers["Location"] == "/signup"
    assert session["_errors"] == {"email": ["required"]}  # flashed to the error bag


def test_web_without_referer_redirects_to_root() -> None:
    r = render_exception(Req({"accept": "text/html"}, session={}), _exc())
    assert r.status_code == 302
    assert r.headers["Location"] == "/"


def test_5xx_is_reported_but_4xx_is_not() -> None:
    """render_exception routes a 5xx through the app's ExceptionHandler.report() (so it leaves a
    server-side log), while a 4xx — an expected client error — stays unreported."""
    from structlog.testing import capture_logs

    from arvel.http.exceptions import HttpException
    from arvel.kernel import Application, set_application
    from arvel.kernel.logging import configure_logging
    from arvel.kernel.provider import KernelServiceProvider

    app = Application()
    KernelServiceProvider(app).register()  # binds "log" + "exceptions"
    set_application(app)
    try:
        configure_logging()
        with capture_logs() as logs:
            render_exception(Req({"accept": "application/json"}), HttpException(500, "boom"))
            render_exception(Req({"accept": "application/json"}), HttpException(404, "nope"))
        events = [log["event"] for log in logs]
        assert events.count("unhandled_exception") == 1  # the 500 is reported, the 404 is not
    finally:
        set_application(None)
