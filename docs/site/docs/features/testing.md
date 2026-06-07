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

Every external-facing facade ships a fake that captures activity instead of performing it, with matching assertions. `Cache` and `Storage` come from `arvel.facades`; `Mail`, `Event`, `Bus`, and `Notification` are submodule facades (`WelcomeMail`, `OrderShipped`, `ship_order`, `SendInvoiceJob`, and `WelcomeEmail` are your own app code):

```python
from arvel.facades import Cache, Storage
from arvel.facades.mail import Mail
from arvel.facades.event import Event
from arvel.facades.bus import Bus
from arvel.facades.notification import Notification

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

### `Bus.fake()` — queue assertions

`Bus.fake()` swaps the active queue connection with an in-memory recorder. Dispatches are captured but never execute, so handlers don't run and external systems aren't touched:

```python
from arvel.facades.bus import Bus

with Bus.fake() as ctx:
    await Bus.dispatch(SendInvoiceJob(invoice_id=42))
    await Bus.chain([SendInvoiceJob(invoice_id=43), MarkAsPaidJob(invoice_id=43)])

    Bus.assert_dispatched(SendInvoiceJob)               # at least once
    Bus.assert_dispatched(SendInvoiceJob, times=2)      # exact count
    Bus.assert_not_dispatched(NeverFiredJob)
    Bus.assert_dispatched_on(SendInvoiceJob, "high")    # routed to a specific queue
    Bus.assert_chained(SendInvoiceJob, MarkAsPaidJob)   # head + ordered tail

    # Raw access to recorded pushes for ad-hoc assertions:
    payloads = [p.envelope.payload for p in ctx.fake.pushed]
```

### `Notification.fake()` — notification assertions

`Notification.fake()` swaps the bound `NotificationManager` with a recorder. Channel work (mail, broadcast, database, log) is skipped:

```python
from arvel.facades.notification import Notification

with Notification.fake():
    await user_service.welcome(user)

    Notification.assert_sent_to(user, WelcomeEmail)
    Notification.assert_sent_to(user, WelcomeEmail, times=1)
    Notification.assert_not_sent_to(user, AccountDeletedEmail)

    # Or, for "nothing happened" tests:
    Notification.assert_nothing_sent()
```

For broadcasting, use `BroadcasterFake` directly — it records each `broadcast(...)` call and exposes `assert_broadcasted(...)` (see [Broadcasting](broadcasting.md#testing)). It's a driver-level fake, not a manager, so it isn't passed to `Broadcast.set_manager(...)`.

<a name="json-http-helpers"></a>
## JSON HTTP helpers

`ArvelTestCase` ships JSON-aware request helpers that set the right `Accept` / `Content-Type` headers and wrap the response in a `TestResponse` with fluent assertions:

```python
class TestApi(ArvelTestCase):
    async def test_create_user(self) -> None:
        response = await self.post_json("/users", {"email": "a@b.com"})
        response.assert_status(201).assert_json_fragment({"email": "a@b.com"})

    async def test_list_users(self) -> None:
        response = await self.get_json("/users?per_page=10")
        response.assert_ok().assert_json_count(10, "data")

    async def test_validation(self) -> None:
        response = await self.post_json("/users", {})
        response.assert_json_validation_errors("email", "name")
```

The helpers: `get_json`, `post_json`, `put_json`, `patch_json`, `delete_json`. Caller-supplied `headers=` merge over the defaults, so per-test overrides work without surprises.

### `TestResponse` JSON assertions

| Method | Purpose |
|---|---|
| `assert_json(expected)` | Body equals `expected` exactly |
| `assert_exact_json(expected)` | Alias of `assert_json` (Laravel-style name) |
| `assert_json_fragment(subset)` | Every key/value in `subset` is present at the root |
| `assert_json_path(path, value)` | Dotted-path lookup equals `value` (e.g. `"user.id"`, `"items.0.name"`) |
| `assert_json_missing(path)` | Dotted path is absent |
| `assert_json_structure(shape)` | Body has the keys described by `shape`; `{"*": [...]}` applies to every list element |
| `assert_json_count(n, path=None)` | Body (or `path`) is a list of `n` items |
| `assert_json_validation_errors(*fields)` | 422 response carries errors for every named field — handles both FastAPI `detail` and Laravel `errors` shapes |

<a name="database-testing"></a>
## Database Testing

### `RefreshDatabase` mixin

`RefreshDatabase` wraps every test in a database transaction and rolls it back at teardown. Whatever the test writes never persists, so tests stay isolated without dropping and re-running migrations on every method.

```python
from arvel.testing import ArvelTestCase, RefreshDatabase
from arvel.providers import DatabaseServiceProvider

class TestPosts(RefreshDatabase, ArvelTestCase):
    providers = (DatabaseServiceProvider,)

    async def test_create(self) -> None:
        await Post.create(title="Hi")
        rows = await Post.all()
        assert [p.title for p in rows] == ["Hi"]
        # The row is rolled back after this test — TestOtherStuff sees an empty table.
```

The mixin requires the app to bind an `AsyncEngine` in its container (which `DatabaseServiceProvider` does). When no engine is bound it's a no-op, so it's safe to apply to tests that don't touch the DB.

Override `seed()` to populate the database before each test:

```python
class TestWithFixtures(RefreshDatabase, ArvelTestCase):
    providers = (DatabaseServiceProvider,)

    async def seed(self) -> None:
        await User.create(email="alice@example.com", password="secret")
        await User.create(email="bob@example.com", password="secret")

    async def test_count(self) -> None:
        assert await User.count() == 2
```

> [!NOTE]
> Schema (tables, columns, indexes) must already exist before the mixin runs — run migrations once in your test session setup or use an in-memory engine fixture that creates them. `RefreshDatabase` only manages row-level state; it doesn't drop or recreate tables.
