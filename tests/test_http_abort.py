"""HTTP — ``abort(status, message?)`` helper raising an ``HttpException`` that the
content-negotiated renderer turns into the right status + message (spec 04 §88). Test-first."""

from __future__ import annotations

import pytest

from arvel.http import HttpException, abort
from arvel.http.exceptions import render_exception


class _Req:
    def __init__(self, accept: str = "application/json") -> None:
        self.headers = {"accept": accept}


def test_abort_raises_http_exception_with_status() -> None:
    with pytest.raises(HttpException) as ei:
        abort(404)
    assert ei.value.status == 404


def test_abort_carries_custom_message() -> None:
    with pytest.raises(HttpException) as ei:
        abort(403, "You shall not pass.")
    assert ei.value.status == 403
    assert str(ei.value) == "You shall not pass."


def test_render_uses_custom_message_and_status() -> None:
    exc = HttpException(403, "You shall not pass.")
    resp = render_exception(_Req(), exc)
    assert resp.status_code == 403
    assert resp.content == {"message": "You shall not pass."}


def test_render_falls_back_to_status_text() -> None:
    resp = render_exception(_Req(), HttpException(404))
    assert resp.status_code == 404
    assert resp.content == {"message": "Not Found"}
