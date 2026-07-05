# Testing

A framework is only as testable as the seams it gives you. Test a real feature and you immediately
need three things: a way to drive the app like a real client, a way to *not* actually send the email
or hit the payment API, and a way to check the database changed. arvel ships all three — a real HTTP
test client that runs your app through the same stack production uses, recording **fakes** for side
effects (mail, queue, events), and database assertions — so a feature test reads like a description
of the behaviour, not a pile of mocks.

This page covers the test client, fakes, database assertions, and freezing time.

!!! note "Test tooling"
    The helpers in `arvel.testing` come with the framework; the test client needs `arvel[http]`, and
    the test runner + factories (pytest, pytest-asyncio, polyfactory, faker) come with `arvel[dev]`.

## Feature tests with the test client

`client(asgi)` wraps Litestar's `TestClient` over your app, so requests run the actual routing,
middleware, and handlers — and every verb call (`get`/`post`/`put`/`patch`/`delete`) returns a
response with expressive assertions instead of a bare status code to check by hand:

```python
from arvel.testing import client

def test_homepage():
    c = client(app.as_asgi())
    c.get("/").assert_ok().assert_see("Welcome")
```

Because it's the real Litestar client, the OpenAPI schema, validation, and middleware all run —
you're testing the app, not a mock of it. `.raw` is the escape hatch to the underlying `httpx`
response for anything not covered below.

### Response assertions

Every assertion returns the response, so they chain:

```python
response = c.post("/users", json={"name": "Ada"})
response.assert_created()
response.assert_json({"data.name": "Ada"})          # subset match — extra keys are tolerated
response.assert_json_path("data.id", 1)              # dotted path into the parsed JSON
response.assert_header("content-type", "application/json")
```

| Assertion | Checks |
|-----------|--------|
| `assert_status(n)` | the exact status code |
| `assert_ok()` / `assert_created()` / `assert_no_content()` | 200 / 201 / 204 |
| `assert_not_found()` / `assert_forbidden()` / `assert_unauthorized()` / `assert_unprocessable()` | 404 / 403 / 401 / 422 |
| `assert_redirect(to=None)` | a 3xx status, and (with `to`) the `Location` header — pass `follow_redirects=False` to the request so the client doesn't chase the redirect itself |
| `assert_json(fragment)` | a dotted-key subset of the parsed JSON (extra keys tolerated) |
| `assert_json_path(path, value)` | one dotted-key value (`"items.0.id"` indexes into a list) |
| `assert_json_count(n, path=None)` | `len(...)` at `path` (or the root) |
| `assert_json_missing(fragment)` | none of the dotted keys are present |
| `assert_see(text)` | the raw body contains `text` |
| `assert_header(name, value=None)` | the header is present (and, with `value`, matches) |

## Fakes: assert side effects without doing them

Swap a recording fake behind a facade and assert what *would* have happened — no email sent, no
job queued, no notification delivered, no real HTTP request made:

```python
from arvel.testing import fake, fake_notifications, fake_http, reset_fakes
from arvel import Mail, Queue, Event

def test_registration_sends_welcome():
    mail = fake(Mail)
    queue = fake(Queue)
    notifications = fake_notifications()

    register_user({"email": "ada@example.com"})

    mail.assert_sent(WelcomeMail)
    queue.assert_pushed(ProvisionWorkspace)
    notifications.assert_sent_to(user, WelcomeAboard)
    reset_fakes()                      # restore real implementations (do this in teardown)
```

| Fake | Assertions |
|------|-----------|
| `fake(Mail)` | `assert_sent(Mailable)` · `assert_nothing_sent()` |
| `fake(Queue)` | `assert_pushed(Job)` · `assert_nothing_pushed()` |
| `fake(Event)` | `assert_dispatched(EventType)` |
| `fake_notifications()` | `assert_sent_to(notifiable, cls, cb=None)` · `assert_not_sent_to(...)` · `assert_nothing_sent()` · `assert_count(n)` |
| `fake_bus()` | same object as `fake(Queue)` — `assert_dispatched(Job)`/`assert_not_dispatched(Job)` (Laravel `Bus::fake` naming; arvel models `Bus`/`Queue` dispatch as the one push path, not two fakes) |
| `fake_http(mapping=None)` | `Http.fake(...)` under the hood, returned for `assert_sent`/`assert_not_sent`/`assert_sent_count`/`recorded` — see [HTTP Client](http-client.md) for the mapping/`Http.response(...)` shape |
| `fake_storage(disk="local")` | see [File Storage](storage.md) |

Call `reset_fakes()` in teardown so a swapped fake doesn't leak into the next test — it restores
every facade swap plus the faked storage disk, HTTP transport, and notification binding.

## Isolating process-global state

The default api-group **rate limiter** and the in-process **session store** are process-global —
correct for one running app, but they persist across the many app instances a suite builds in one
process, so the throttle eventually returns a spurious `429` mid-suite. Reset them between tests:

```python
import pytest
from arvel.http import reset_rate_limiter, reset_sessions

@pytest.fixture(autouse=True)
def _isolate():
    reset_rate_limiter()   # clear the in-process rate-limit windows
    reset_sessions()       # clear the in-process session store
    yield
```

(No effect on a cache-backed limiter/session store — clear that backend instead.)

## Database assertions

Assert rows exist, don't exist, or are soft-deleted — straight against the connection:

```python
from arvel.testing import assert_database_has, assert_database_missing, assert_soft_deleted

async def test_create_and_delete(db):
    await create_post(db, title="Hello")
    await assert_database_has(db, "posts", title="Hello")

    await delete_post(db, title="Hello")
    await assert_soft_deleted(db, "posts", title="Hello")     # deleted_at is set
    await assert_database_missing(db, "audit_log", action="purge")
```

## Console commands

`artisan(app, command, input=None)` runs an app-registered command (a `Command` class on
`app.command_classes`, or a `routes/console.py` `Console.command(...)` closure) against a booted
app and captures its exit code + output — Laravel's `$this->artisan(...)`:

```python
from arvel.testing import artisan

def test_greet_command(app):
    result = artisan(app, "greet Ada --loud", input=["Bob"])   # input pre-seeds ask()/confirm()/...
    result.assert_exit_code(0).assert_output_contains("hello Bob")
```

`input` answers prompts (`Command.ask`/`secret`/`confirm`/`choice`/`anticipate`) in the order
they're asked — an exhausted or empty seeded answer falls back to the prompt's own default, same as
a real `Prompter`.

!!! note "Built-in framework commands aren't reachable this way"
    `artisan()` only dispatches **your** commands (app/provider `Command` classes and
    `Console.command(...)` closures) — a built-in (`migrate`, `make:*`, `db:seed`, ...) isn't. Test
    those with Typer's own `CliRunner` directly:

    ```python
    from typer.testing import CliRunner
    from arvel.console import build_cli

    result = CliRunner().invoke(build_cli(), ["route:list"])
    assert result.exit_code == 0
    ```

## Freezing time

Make time-dependent behavior deterministic by pinning "now" — isolated per async test (see
[Dates & Time](dates.md)):

```python
from arvel.dates import Date

def test_token_expiry():
    Date.set_test_now(Date.parse("2026-01-01T00:00:00+00:00"))
    try:
        token = issue_token()
        assert token.expires_at == Date.parse("2026-01-01T01:00:00+00:00")
    finally:
        Date.set_test_now(None)
```

## How tests are run

The suite runs under `pytest` (async mode auto). The project's quality gate — `ruff`, `mypy`
and `pyright` (strict), `import-linter`, `bandit`, the tests, and a line-coverage floor — is one
command (`make check` / `./tools/validate.sh`), the same gate CI enforces.

### Integration tests (real services)

The unit suite uses fakes/SQLite; an opt-in **integration tier** exercises arvel against *real*
infrastructure spun up on demand via [testcontainers](https://testcontainers.com) (needs Docker).
Run it with `make test-integration` (or `pytest -m integration`). It covers PostgreSQL (+ pgvector),
**MySQL** (the ORM + real `DATETIME` round-trips), Redis (cache/session/throttle), object storage
(RustFS/S3 + Azurite), a real **AMQP broker** (RabbitMQ/LavinMQ — a job dispatched, consumed, and
executed end to end), and **OpenTelemetry** export to a live OTLP collector. These catch what fakes
can't — e.g. cross-dialect DDL, broker serialization, and real wire protocols.

It also includes a **reference app** (`test_reference_app.py`): a small project/task API — token auth,
validated CRUD, pagination, a model relationship, and a queued job — assembled through the production
fluent bootstrap and driven over HTTP against live PostgreSQL + Redis + RabbitMQ at once, proving the
features *compose* on real infrastructure, not just in isolation.

## Common mistakes & gotchas

- **Leaking a fake or a frozen clock.** Always `reset_fakes()` and `Date.set_test_now(None)` in
  teardown — a leak makes an unrelated later test fail mysteriously.
- **Asserting on a fake you didn't swap.** `assert_pushed` only sees jobs after `fake(Queue)`;
  without the swap they run for real and the assertion has nothing recorded.
- **Mocking the framework.** You rarely need to — the test client runs the real stack and the
  fakes cover the I/O edges. Reach for a mock only at a genuine third-party boundary.

## See also

- [Dates & Time](dates.md) — freezing time. [Queues & Jobs](queues.md) · [Mail](mail.md) —
  what the fakes record.
