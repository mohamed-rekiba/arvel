"""Custom HTTP error pages: resources/views/errors/<status>.html rendered for HTML clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from arvel.http.exceptions import HttpException, render_exception


@dataclass
class Req:
    _headers: dict[str, str] = field(default_factory=dict)
    session: dict[str, Any] | None = None

    @property
    def headers(self) -> dict[str, str]:
        return self._headers


def _html_req() -> Req:
    return Req({"accept": "text/html"})


def test_custom_error_page_is_rendered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    errors = tmp_path / "resources" / "views" / "errors"
    errors.mkdir(parents=True)
    (errors / "404.html").write_text("<h1>lost: {{ status }}</h1><p>{{ message }}</p>")
    monkeypatch.chdir(tmp_path)

    r = render_exception(_html_req(), HttpException(404, "no such thing"))

    assert r.status_code == 404
    assert r.media_type == "text/html"
    assert "lost: 404" in r.content
    assert "no such thing" in r.content


def test_generic_fallback_page_covers_unlisted_statuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    errors = tmp_path / "resources" / "views" / "errors"
    errors.mkdir(parents=True)
    (errors / "generic.html").write_text("<h1>oops {{ status }}</h1>")
    monkeypatch.chdir(tmp_path)

    r = render_exception(_html_req(), HttpException(503, "down for maintenance"))

    assert r.status_code == 503
    assert "oops 503" in r.content


def test_falls_back_to_builtin_page_when_no_template(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # no resources/views/errors here

    r = render_exception(_html_req(), HttpException(404))

    assert r.status_code == 404
    assert "<h1>404" in r.content  # the built-in minimal page
