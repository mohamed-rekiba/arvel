"""3.5 client-retry-fill: backoff sequences/callables, `throw=False`, `ClientResponse.throw_if`,
`on_error(hook)`, faked response sequences, and `pool(max_concurrency=...)`. Test-first."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from arvel.client import (
    Client,
    ClientResponse,
    FakeSequenceExhausted,
    RequestFailed,
    TransportFailed,
)
from arvel.support import Sleep


class _FlakyTransport(httpx.AsyncBaseTransport):
    def __init__(self, outcomes: list[Exception | httpx.Response]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


# --- backoff sequences / callables --------------------------------------------------------


async def test_retry_backoff_sequence_used_between_attempts() -> None:
    transport = _FlakyTransport(
        [httpx.Response(500), httpx.Response(500), httpx.Response(200, json={"ok": True})]
    )
    client = Client(transport=transport)
    with Sleep.fake() as recorded:
        response = await client.retry(3, backoff=[0.1, 0.5]).get("https://x.test/flaky")
    assert response.status() == 200
    assert recorded == [0.1, 0.5]


async def test_retry_backoff_sequence_repeats_the_last_entry_past_its_length() -> None:
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(500), httpx.Response(200)])
    client = Client(transport=transport)
    with Sleep.fake() as recorded:
        await client.retry(3, backoff=[0.2]).get("https://x.test/flaky")
    assert recorded == [0.2, 0.2]


async def test_retry_backoff_callable_receives_the_1_based_attempt() -> None:
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(500), httpx.Response(200)])
    client = Client(transport=transport)
    seen: list[int] = []

    def backoff(attempt: int) -> float:
        seen.append(attempt)
        return attempt * 0.01

    with Sleep.fake() as recorded:
        await client.retry(3, backoff=backoff).get("https://x.test/flaky")
    assert seen == [1, 2]
    assert recorded == [0.01, 0.02]


# --- throw=False -----------------------------------------------------------------------


async def test_retry_throw_false_returns_last_response_instead_of_raising() -> None:
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(500)])
    client = Client(transport=transport)
    response = await client.retry(2, 0, throw=False).get("https://x.test/flaky")
    assert response.status() == 500
    assert transport.calls == 2


async def test_retry_throw_false_still_raises_on_a_connect_error() -> None:
    transport = _FlakyTransport([httpx.ConnectError("boom"), httpx.ConnectError("boom again")])
    client = Client(transport=transport)
    with pytest.raises(TransportFailed):  # engine connect error, wrapped in arvel's taxonomy
        await client.retry(2, 0, throw=False).get("https://x.test/flaky")


async def test_retry_throw_true_is_still_the_default() -> None:
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(500)])
    client = Client(transport=transport)
    with pytest.raises(RequestFailed):
        await client.retry(2, 0).get("https://x.test/flaky")


# --- ClientResponse.throw_if -------------------------------------------------------------


async def test_throw_if_raises_on_truthy_bool() -> None:
    transport = _FlakyTransport([httpx.Response(200)])
    client = Client(transport=transport)
    response = await client.get("https://x.test/ok")
    with pytest.raises(RequestFailed):
        response.throw_if(True)


async def test_throw_if_predicate_over_response() -> None:
    transport = _FlakyTransport([httpx.Response(200, json={"warn": True})])
    client = Client(transport=transport)
    response = await client.get("https://x.test/ok")
    with pytest.raises(RequestFailed):
        response.throw_if(lambda r: r.json("warn") is True)


async def test_throw_if_falsy_is_a_no_op_and_chainable() -> None:
    transport = _FlakyTransport([httpx.Response(200, json={"ok": 1})])
    client = Client(transport=transport)
    response = await client.get("https://x.test/ok")
    assert response.throw_if(False).json() == {"ok": 1}


# --- on_error(hook) ------------------------------------------------------------------------


async def test_on_error_hook_called_once_per_retry_worthy_attempt() -> None:
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(500), httpx.Response(200)])
    client = Client(transport=transport)
    seen: list[Any] = []

    def hook(outcome: Any) -> None:
        seen.append(outcome.status() if isinstance(outcome, ClientResponse) else outcome)

    with Sleep.fake():
        await client.retry(3, 0).on_error(hook).get("https://x.test/flaky")
    assert seen == [500, 500]


async def test_on_error_hook_fires_even_on_the_final_exhausted_attempt() -> None:
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(500)])
    client = Client(transport=transport)
    seen: list[Any] = []

    with Sleep.fake(), pytest.raises(RequestFailed):
        await client.retry(2, 0).on_error(lambda o: seen.append(o)).get("https://x.test/flaky")
    assert len(seen) == 2


async def test_on_error_hook_may_be_async() -> None:
    transport = _FlakyTransport([httpx.Response(500), httpx.Response(200)])
    client = Client(transport=transport)
    seen: list[Any] = []

    async def hook(outcome: Any) -> None:
        seen.append(outcome)

    with Sleep.fake():
        await client.retry(2, 0).on_error(hook).get("https://x.test/flaky")
    assert len(seen) == 1


async def test_on_error_not_called_when_nothing_fails() -> None:
    transport = _FlakyTransport([httpx.Response(200)])
    client = Client(transport=transport)
    seen: list[Any] = []
    await client.retry(3, 0).on_error(lambda o: seen.append(o)).get("https://x.test/ok")
    assert seen == []


# --- faked response sequences --------------------------------------------------------------


async def test_fake_sequence_pops_successive_responses() -> None:
    client = Client()
    with client.fake(
        {"https://x.test/*": [client.response(status=500), client.response(status=200)]}
    ):
        first = await client.get("https://x.test/a")
        second = await client.get("https://x.test/a")
    assert first.status() == 500
    assert second.status() == 200


async def test_fake_sequence_exhaustion_raises() -> None:
    client = Client()
    with client.fake({"https://x.test/*": [client.response(status=200)]}):
        await client.get("https://x.test/a")
        with pytest.raises(FakeSequenceExhausted):
            await client.get("https://x.test/a")


async def test_fake_plain_mapping_still_works_alongside_sequences() -> None:
    client = Client()
    with client.fake(
        {
            "https://x.test/seq": [client.response(status=201)],
            "https://x.test/plain": client.response(status=204),
        }
    ):
        assert (await client.get("https://x.test/seq")).status() == 201
        assert (await client.get("https://x.test/plain")).status() == 204
        assert (await client.get("https://x.test/plain")).status() == 204  # not exhausted


# --- pool concurrency cap --------------------------------------------------------------


async def test_pool_max_concurrency_caps_in_flight_requests() -> None:
    in_flight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    await client.pool(
        lambda pool: [pool.get(f"https://x.test/{i}") for i in range(6)],
        max_concurrency=2,
    )
    assert peak <= 2


async def test_pool_without_max_concurrency_is_unbounded() -> None:
    in_flight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200)

    client = Client(transport=httpx.MockTransport(handler))
    await client.pool(lambda pool: [pool.get(f"https://x.test/{i}") for i in range(6)])
    assert peak == 6
