# Mocking

When testing Arvel applications, you often want to "mock" certain things so that they're not actually executed during the test. For example, when testing a controller that dispatches an event, you may want to mock the event listeners so they're not actually called during the test. This way, you can test the controller's response without worrying about the listeners — since they can be tested in their own test cases.

Every Arvel facade exposes a `fake()` helper for exactly this purpose.

## The pattern

```python
async def test_signup_does_things(client) -> None:
    Mail.fake()
    Bus.fake()
    Notification.fake()
    Event.fake()

    response = await client.post("/signup", json={"email": "a@b.com"})

    Mail.assert_sent(WelcomeEmail)
    Bus.assert_dispatched(SendWelcomeEmail)
```

Calling `Fake.fake()` swaps the facade's backing service with an in-memory recorder for the rest of the test. Nothing is actually sent; the recorder captures intent.

The default test fixture clears all fakes at the end of each test, so you don't need teardown.

## Mail

```python
Mail.fake()

# ... code that calls Mail.to(...).send(...)

Mail.assert_sent(WelcomeEmail)
Mail.assert_sent(WelcomeEmail, lambda m: m.user_name == "Alice")
Mail.assert_count(1)
Mail.assert_to("a@b.com", WelcomeEmail)
Mail.assert_not_sent(BillingNotificationEmail)
```

For asserting on raw recipients without checking the Mailable class:

```python
Mail.assert_sent_to("a@b.com")
```

## Bus (queue)

```python
Bus.fake()

# ... code that calls Bus.dispatch(...)

Bus.assert_dispatched(SendWelcomeEmail)
Bus.assert_dispatched(SendWelcomeEmail, lambda job: job.user_id == 42)
Bus.assert_dispatched_count(SendWelcomeEmail, 1)
Bus.assert_not_dispatched(ChargeCard)
```

To run a specific job through the real handler even under `fake()`:

```python
Bus.fake_except([SendWelcomeEmail])
```

## Notification

```python
Notification.fake()

await user.notify(OrderShipped(order_id=42))

Notification.assert_sent_to(user, OrderShipped)
Notification.assert_sent_on(user, "mail", OrderShipped)
Notification.assert_count(1)
Notification.assert_nothing_sent_to(other_user)
```

## Event

```python
Event.fake()

await Event.dispatch(OrderCompleted(order_id=42, ...))

Event.assert_dispatched(OrderCompleted)
Event.assert_dispatched(OrderCompleted, lambda e: e.order_id == 42)
Event.assert_dispatched_count(OrderCompleted, 1)
Event.assert_not_dispatched(SuspiciousActivityDetected)
```

To run a subset of listeners normally:

```python
Event.fake_except([OrderCompleted])
```

## Storage

```python
Storage.fake("local")     # in-memory filesystem mounted as "local"

# ... code that calls Storage.disk("local").put(...)

Storage.disk("local").assert_exists("avatars/alice.png")
Storage.disk("local").assert_missing("avatars/bob.png")
```

The fake disk records everything in memory; it's discarded at end of test.

## Cache

The cache layer has a dedicated test driver — set it in `.env.testing`:

```env
CACHE_DRIVER=array
```

The `array` driver is in-process and per-test-isolated by default (the framework flushes it after each test via the standard fixture).

## HTTP client

```python
Http.fake({
    "GET https://api.example.com/users/42": Http.response(json={"id": 42}),
    "POST https://api.example.com/orders": Http.response(json={"id": "ord_1"}, status=201),
})

# ... code that calls Http.get/post(...)

Http.assert_sent(lambda req: "users/42" in req.url)
Http.assert_count(2)
```

Any request that doesn't match a fake response raises `UnexpectedHttpRequest`. So if your test makes a network call you didn't expect, you'll know immediately.

## Time

```python
from arvel.testing import freeze_time


with freeze_time("2026-01-01T00:00:00Z"):
    # everything calling now() inside this block sees 2026-01-01 00:00 UTC
    ...
```

For relative travel:

```python
from arvel.testing import travel


async def test_token_expires() -> None:
    token = sign_token(...)

    await travel(hours=1, minutes=1)
    with pytest.raises(ExpiredSignature):
        verify_token(token)
```

## Container swaps

For ad-hoc dependency swaps that the framework doesn't ship a `fake()` for:

```python
async def test_uses_fake_payment_gateway(app):
    app.container.instance(PaymentGateway, FakePaymentGateway())
    ...
```

The fixture that built the app teardown-restores the original bindings.

## Where to next?

- [HTTP Tests](http-tests.md) — combining fakes with HTTP assertions.
- [Database](database.md) — per-test rollback.
- [Testing → Getting Started](index.md) — the basics.
