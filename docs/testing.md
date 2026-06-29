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
middleware, and handlers:

```python
from arvel.testing import client

def test_homepage():
    c = client(app.as_asgi())
    response = c.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.text
```

Because it's the real Litestar client, the OpenAPI schema, validation, and middleware all run —
you're testing the app, not a mock of it.

## Fakes: assert side effects without doing them

Swap a recording fake behind a facade and assert what *would* have happened — no email sent, no
job queued:

```python
from arvel.testing import fake, reset_fakes
from arvel import Mail, Queue, Event

def test_registration_sends_welcome():
    mail = fake(Mail)
    queue = fake(Queue)

    register_user({"email": "ada@example.com"})

    mail.assert_sent(WelcomeMail)
    queue.assert_pushed(ProvisionWorkspace)
    reset_fakes()                      # restore real implementations (do this in teardown)
```

| Fake | Assertions |
|------|-----------|
| `fake(Mail)` | `assert_sent(Mailable)` · `assert_nothing_sent()` |
| `fake(Queue)` | `assert_pushed(Job)` · `assert_nothing_pushed()` |
| `fake(Event)` | `assert_dispatched(EventType)` |

Call `reset_fakes()` in teardown so a swapped fake doesn't leak into the next test.

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
