# Testing: Getting Started

Arvel is built with testing in mind — every facade has a fake, the container can be swapped per test, and HTTP requests can be exercised end to end without spinning up a real server. Tests run under [pytest](https://docs.pytest.org/) with [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) for async support.

## Project layout

The starter template ships:

```
tests/
├── conftest.py        # shared fixtures (test client, DB rollback, app factory)
├── unit/              # fast tests, no I/O
└── feature/           # HTTP / job / mail / broadcast tests
```

You're free to structure differently — `unit/` vs `feature/` is convention, not requirement.

## Running tests

```bash
uv run pytest                       # everything
uv run pytest tests/feature/        # only feature tests
uv run pytest -k user_signup        # name filter
uv run pytest --cov=app             # with coverage
```

For watch mode during development, use [pytest-watcher](https://github.com/olzhasar/pytest-watcher):

```bash
uv tool install pytest-watcher
uv run ptw -- tests/
```

## The basic test

```python
import pytest


@pytest.mark.anyio
async def test_addition() -> None:
    assert 1 + 1 == 2
```

`@pytest.mark.anyio` opts the test into the async runtime. Configure pytest to default-enable it in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Then you can drop the marker:

```python
async def test_addition() -> None:
    assert 1 + 1 == 2
```

## The application fixture

```python
# tests/conftest.py
import pytest
from arvel import Application


@pytest.fixture
async def app() -> Application:
    app = Application.configure(".").with_environment("testing").create()
    await app.boot()
    yield app
    await app.shutdown()
```

The `testing` environment is identical to `local` except that:

- It loads `.env.testing` for environment-specific overrides.
- It refuses to run destructive commands (`migrate:fresh`) in production without `ARVEL_ALLOW_DESTRUCTIVE=1`.
- It defaults the cache, queue, mail, and storage drivers to in-memory equivalents.

## The HTTP test client

```python
@pytest.fixture
async def client(app):
    from httpx import AsyncClient
    from httpx_ws.transport import ASGITransport

    transport = ASGITransport(app=app.into_asgi())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_hello(client) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "hello from arvel"}
```

The client speaks HTTPX semantics — `client.get(...)`, `client.post(..., json={...})`, headers, cookies — without ever opening a socket.

## Faking facades

Every external-facing facade has a `fake()` helper that swaps the underlying driver for an in-memory recorder:

```python
async def test_signup_sends_welcome_email(client) -> None:
    Mail.fake()
    Bus.fake()
    Notification.fake()
    Event.fake()

    response = await client.post("/signup", json={"name": "Alice", "email": "a@b.com"})
    assert response.status_code == 201

    Mail.assert_sent(WelcomeEmail)
    Bus.assert_dispatched(SendWelcomeEmail)
```

See [Mocking](mocking.md) for the full set of helpers.

## Asserting against the database

```python
async def test_signup_creates_user(client) -> None:
    response = await client.post("/signup", json={"name": "Alice", "email": "a@b.com"})
    assert response.status_code == 201

    user = await User.where(email="a@b.com").first()
    assert user is not None
    assert user.name == "Alice"
```

For per-test database isolation, see [Database tests](database.md).

## Authenticated tests

```python
async def test_me_returns_authenticated_user(client) -> None:
    user = await UserFactory().create()
    response = await client.get("/me", headers={"Authorization": f"Bearer {issue_jwt(user)}"})
    assert response.status_code == 200
    assert response.json()["email"] == user.email
```

For a higher-level shortcut, use `Auth.login(user)` and the test client's session:

```python
async def test_dashboard(client) -> None:
    user = await UserFactory().create()
    Auth.login(user)
    response = await client.get("/dashboard")
    assert response.status_code == 200
```

## Testing background jobs

```python
async def test_send_welcome_email_handler() -> None:
    user = await UserFactory().create()
    Mail.fake()

    await SendWelcomeEmail(user_id=user.id).handle()

    Mail.assert_sent(WelcomeEmail, lambda m: m.user_name == user.name)
```

Run the job's `handle()` directly — no queue, no worker.

## Time travel

For tests that depend on the clock, use `freeze_time`:

```python
from arvel.testing import freeze_time


async def test_token_expires() -> None:
    with freeze_time("2026-01-01T00:00:00Z"):
        token = sign_token(...)

    with freeze_time("2026-01-01T01:01:00Z"):    # 1 hour 1 min later
        with pytest.raises(ExpiredSignature):
            verify_token(token)
```

## Testing framework components with `create_test_app`

When writing tests for middleware, service providers, or other framework components, use `create_test_app()` to boot a minimal ASGI application in-process. It calls `boot()` and `shutdown()` automatically, so lifecycle hooks are exercised correctly.

```python
import pytest
from arvel.testing import create_test_app


@pytest.mark.asyncio
async def test_my_middleware_adds_header() -> None:
    from starlette.responses import Response

    class MinimalApp:
        async def boot(self) -> None: ...
        async def shutdown(self) -> None: ...

        def into_asgi(self):
            from arvel.http.middleware import SecurityHeadersMiddleware
            from starlette.types import Receive, Scope, Send

            async def inner(scope: Scope, receive: Receive, send: Send) -> None:
                await Response("ok")(scope, receive, send)

            return SecurityHeadersMiddleware(inner)

    async with create_test_app(MinimalApp()) as client:
        response = await client.get("http://test/")
        assert "strict-transport-security" in response.headers
```

`create_test_app()` returns an `httpx.AsyncClient` pre-wired to the app's ASGI interface. No sockets, no ports. The `async with` block ensures `shutdown()` is called even if the test raises.

## Where to next?

- [HTTP Tests](http-tests.md) — testing endpoints in depth.
- [Database](database.md) — per-test rollback, factories.
- [Mocking](mocking.md) — the full facade-fake catalog.
