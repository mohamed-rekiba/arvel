"""wants_json content negotiation."""

from __future__ import annotations


class _FakeRequest:
    def __init__(self, *, headers: dict[str, str] | None = None, path: str = "/") -> None:
        self.headers = headers or {}
        self.url = _FakeURL(path)


class _FakeURL:
    def __init__(self, path: str) -> None:
        self.path = path


def test_wants_json_true_for_api_path() -> None:
    from arvel.http.negotiation import wants_json

    assert wants_json(_FakeRequest(path="/api/users")) is True


def test_wants_json_true_for_accept_json() -> None:
    from arvel.http.negotiation import wants_json

    assert wants_json(_FakeRequest(headers={"accept": "application/json"})) is True


def test_wants_json_true_when_json_appears_in_compound_accept() -> None:
    from arvel.http.negotiation import wants_json

    assert wants_json(_FakeRequest(headers={"accept": "text/html, application/json;q=0.9"})) is True


def test_wants_json_true_for_xhr() -> None:
    from arvel.http.negotiation import wants_json

    assert wants_json(_FakeRequest(headers={"x-requested-with": "XMLHttpRequest"})) is True


def test_wants_json_false_for_browser() -> None:
    from arvel.http.negotiation import wants_json

    assert wants_json(_FakeRequest(headers={"accept": "text/html"})) is False
