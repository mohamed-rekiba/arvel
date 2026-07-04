"""The ``Http`` facade forwards builders/verbs/pool/fake to the container-resolved ``Client``
(``arvel.support.facades.Http``). ``fake`` gets an explicit override there — the base ``Facade``
already defines a zero-arg ``fake()`` for the generic swap-in-a-fake-implementation pattern, so
``Http`` needs its own to accept the URL→stub mapping (spec 07 §4)."""

from __future__ import annotations

from typing import Any

from arvel.client import Client
from arvel.kernel.globals import set_application
from arvel.support.facades import Http


class _FakeApp:
    def __init__(self, bindings: dict[str, Any]) -> None:
        self._b = bindings

    def make(self, key: str) -> Any:
        return self._b[key]

    def bound(self, key: str) -> bool:
        return key in self._b


async def test_http_facade_fake_and_restore() -> None:
    client = Client()
    set_application(_FakeApp({"http": client}))
    try:
        with Http.fake({"https://example.com/*": Http.response(body="stubbed")}):
            response = await Http.get("https://example.com/x")
            assert response.body() == "stubbed"
            Http.assert_sent(lambda r: r.url == "https://example.com/x")
        Http.assert_sent_count(0)  # restored — no fake state, so nothing recorded post-exit
    finally:
        set_application(None)


async def test_http_facade_builders_and_verbs_forward_to_the_resolved_client() -> None:
    client = Client()
    set_application(_FakeApp({"http": client}))
    try:
        with Http.fake({"https://api.test/*": Http.response(body={"id": 7})}):
            response = await Http.with_token("t").timeout(5).accept_json().get("https://api.test/x")
            assert response.json() == {"id": 7}
    finally:
        set_application(None)
