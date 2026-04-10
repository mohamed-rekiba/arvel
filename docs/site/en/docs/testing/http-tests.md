# HTTP Tests

HTTP tests are where Arvel shines: you exercise the same code paths a user hits—routing, middleware, guards, validation—without standing up a separate server. The **`TestClient`** wraps **`httpx.AsyncClient`** with ASGI transport, so each call runs through your app as if it arrived over the wire. Responses come back as **`TestResponse`**, which adds opinionated assertion helpers on top of a normal **`httpx.Response`**.

If you have written feature tests in Laravel, think of this as the async, type-friendly cousin. You still ask “did we get a 201?”, “is the JSON shape right?”, “did the redirect land where we expected?”—you just **`await`** the request and chain assertions.

## Creating a client

Always open **`TestClient`** with `async with`. That spins up the httpx client and tears it down cleanly. The default base URL is `http://testserver`; you can pass another if your routes assume a specific host.

```python
from arvel.testing import TestClient

from myapp.main import app


async def example():
    async with TestClient(app) as client:
        response = await client.get("/posts")
    # client closed here
```

Inside the block, use `await client.get(...)`, `post`, `put`, `patch`, or `delete` with the same optional arguments you would pass to httpx (params, json, files, headers, cookies, timeouts, and so on).

## Making requests

**GET** with query parameters:

```python
response = await client.get("/search", params={"q": "arvel"})
```

**POST** with JSON:

```python
response = await client.post(
    "/posts",
    json={"title": "Hello", "body": "Async-first framework"},
)
```

**Multipart** uploads use httpx’s `files=` and `data=` as usual—your validation and controller code see the same shapes they would in production.

## Asserting responses

`TestResponse` is built for fluent chains. Common entry points:

- **`assert_status(code)`** — exact status match, with a snippet of the body on failure.
- **`assert_ok()`** — shorthand for 200.
- **`assert_created()`** — 201.
- **`assert_no_content()`** — 204.
- **`assert_not_found()`** — 404.
- **`assert_unprocessable()`** — 422 (validation errors).

For JSON, you can compare the whole payload or drill into nested data with dot paths and numeric segments for lists:

```python
response = await client.get("/posts/1")

(
    response.assert_ok()
    .assert_json_path("title", "Hello")
    .assert_json_path("comments.0.author", "Ada")
)
```

Use **`assert_json_structure`** when you care about keys existing but not exact values, and **`assert_json_missing`** when a field must not leak into the response.

Redirects and headers have first-class support:

```python
response.assert_redirect("/login")
response.assert_header("cache-control", "no-store")
response.assert_cookie("session_id")
```

Because `TestResponse` delegates unknown attributes to **`httpx.Response`**, you can always fall back to **`response.json()`**, **`response.text`**, or **`response.headers`** when you need something bespoke.

## Auth context with `acting_as`

Many apps resolve the current user from headers or signed tokens. **`TestClient.acting_as`** sets headers that persist for the lifetime of that client session—handy for simulating “logged in as user 42” without hand-rolling auth every call.

```python
async with TestClient(app) as client:
    client.acting_as(user_id=42)
    me = await client.get("/me")
    me.assert_ok()

    client.acting_as(user_id=7, headers={"Authorization": "Bearer test-token"})
    other = await client.get("/admin/dashboard")
```

When you pass **`user_id`**, the client adds an **`X-User-ID`** header if you have not already set one—wire your test auth middleware or dependency to read that in non-production environments. You can also pass arbitrary **`headers`** for bearer tokens, API keys, or tenant identifiers.

## Putting it together

A compact feature test often reads like a short story: arrange application state (database seed or factory), act with `TestClient`, assert with **`TestResponse`**. Keep one logical behavior per test, name tests so failures read well in CI (`test_guest_cannot_delete_post_returns_403`), and prefer asserting status, body, and one security-relevant header when the endpoint is sensitive.

That combination—real ASGI stack, fluent assertions, explicit auth context—is what makes HTTP tests in Arvel feel as productive as the frameworks that inspired it, with async correctness baked in.
