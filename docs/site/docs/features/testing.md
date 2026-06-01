# Testing

<a name="introduction"></a>
## Introduction

Arvel is built with testing in mind. Tests run the real app in-process over ASGI — no network, no separate server — and the framework ships fluent response assertions plus fakes for every external-facing service. Tests are async; use `pytest` with `pytest-asyncio` in auto mode.

<a name="creating-a-test-app"></a>
## Creating a Test App

There are two entry points: a context manager for quick, functional tests, and a base class for class-style suites.

<a name="using-create_test_app"></a>
### Using create_test_app

`create_test_app` boots an `Application`, yields an `httpx.AsyncClient` wired to it over ASGI, and shuts down on exit — even if the test raises:

```python
from arvel.testing import create_test_app


async def test_health() -> None:
    async with create_test_app(app) as client:
        response = await client.get("/health")
        assert response.status_code == 200
```

<a name="using-arveltestcase"></a>
### Using ArvelTestCase

Subclass `ArvelTestCase` for class-style suites. Override `providers` to add the providers your test needs; `asyncSetUp` builds a minimal app (config + HTTP) and an `AsyncClient`, and `asyncTearDown` cleans both up:

```python
from arvel.testing import ArvelTestCase


class TestPosts(ArvelTestCase):
    providers = (MyServiceProvider,)

    async def test_list(self) -> None:
        response = await self.client.get("/posts")
        assert response.status_code == 200
```

<a name="testing-http-requests"></a>
## Testing HTTP Requests

The client is a standard `httpx.AsyncClient`, so all the usual verbs work:

```python
response = await client.post("/posts", json={"title": "Hello"})
```

<a name="response-assertions"></a>
### Response Assertions

Wrap a response in `TestResponse` for fluent, chainable assertions:

```python
from arvel.testing import TestResponse

result = TestResponse(await client.post("/posts", json={"title": "Hello"}))
result.assert_status(201).assert_json_path("data.title", "Hello")
```

Available assertions:

| Method | Checks |
|---|---|
| `assert_ok()` | Status is 2xx |
| `assert_status(code)` | Status equals `code` |
| `assert_unauthorized()` | Status is 401 |
| `assert_forbidden()` | Status is 403 |
| `assert_not_found()` | Status is 404 |
| `assert_redirect(to=None)` | Status is 3xx (and `Location` matches `to`) |
| `assert_json(expected)` | Body equals `expected` exactly |
| `assert_json_path(path, value)` | Dotted path resolves to `value` (supports list indices) |
| `assert_header(name, value=None)` | Header present (and equals `value`) |
| `assert_cookie(name)` | Cookie present |

Every assertion returns `self`, so they chain.

<a name="authenticating-as-a-user"></a>
## Authenticating as a User

`ArvelTestCase.acting_as(user)` authenticates subsequent requests as a user. It's strictly test-only and refuses to run unless the app environment is `testing`:

```python
await self.acting_as(user)
response = await self.client.get("/me")
```

<a name="faking-services"></a>
## Faking Services

Every external-facing facade ships a fake that captures activity instead of performing it, with matching assertions. `Cache` and `Storage` come from `arvel.facades`; `Mail` and `Event` are submodule facades (`WelcomeMail`, `OrderShipped`, and `ship_order` are your own app code):

```python
from arvel.facades import Cache, Storage
from arvel.facades.mail import Mail
from arvel.facades.event import Event

with Cache.fake():
    await Cache.put("k", "v", ttl=60)
    Cache.assert_stored("k")

with Mail.fake() as mailbox:
    await Mail.to("a@b.com").send(WelcomeMail("Ada"))
    assert len(mailbox.sent) == 1

with Storage.fake():
    await Storage.disk().put("f.txt", b"...")
    Storage.assert_exists("f.txt")

with Event.fake():
    await ship_order(order)
    Event.assert_dispatched(OrderShipped)
```

For broadcasting, use `BroadcasterFake` directly — it records each `broadcast(...)` call and exposes `assert_broadcasted(...)` (see [Broadcasting](broadcasting.md#testing)). It's a driver-level fake, not a manager, so it isn't passed to `Broadcast.set_manager(...)`.

<a name="database-testing"></a>
## Database Testing

`ArvelTestCase.refresh_database()` rolls back and re-applies migrations against the testing database between tests.

> [!WARNING]
> `refresh_database()` is **opt-in and partial** — it only acts when the app has bound a database connection and the framework exposes a `refresh_database` helper. Otherwise it's a safe no-op. Don't assume a clean database from it alone; manage test data explicitly until the helper is fully wired.
