# HTTP Tests

The test client lets you exercise your application's HTTP layer end to end — routing, middleware, request validation, response shaping — without ever opening a socket. Tests run in-process via Starlette's ASGI transport.

## Making requests

```python
async def test_get(client):
    response = await client.get("/users")
    assert response.status_code == 200


async def test_post_json(client):
    response = await client.post("/users", json={"name": "Alice", "email": "a@b.com"})
    assert response.status_code == 201


async def test_post_form(client):
    response = await client.post("/login", data={"username": "alice", "password": "..."})
    assert response.status_code == 200


async def test_with_headers(client):
    response = await client.get("/me", headers={"Authorization": "Bearer ..."})
    assert response.status_code == 200
```

## Asserting on responses

```python
response = await client.get("/users/42")

assert response.status_code == 200
assert response.headers["content-type"] == "application/json"
assert response.json() == {"id": 42, "name": "Alice"}

# Pydantic-style structured assertions
data = response.json()
assert data["id"] == 42
assert "email" in data
```

For richer assertions, use a JSON schema or a Pydantic model:

```python
from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    name: str
    email: str


async def test_show_user_shape(client):
    response = await client.get("/users/42")
    user = UserOut.model_validate(response.json())   # raises if shape is wrong
    assert user.id == 42
```

## Validation errors

```python
async def test_signup_validates_email(client):
    response = await client.post("/users", json={"name": "Alice", "email": "not-an-email"})
    assert response.status_code == 422

    errors = response.json()["error"]["details"]
    assert any(err["field"] == "email" for err in errors)
```

## Authentication

```python
async def test_protected_route_requires_login(client):
    response = await client.get("/dashboard")
    assert response.status_code == 401


async def test_protected_route_with_login(client):
    user = await UserFactory().create()
    Auth.login(user)

    response = await client.get("/dashboard")
    assert response.status_code == 200


async def test_with_bearer_token(client):
    user = await UserFactory().create()
    token = await Auth.guard("api").issue_token(subject=str(user.id), expires_in=timedelta(hours=1))

    response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
```

## CSRF in tests

CSRF middleware is bypassed by default in the test environment. To enable CSRF checks for a specific test:

```python
async def test_csrf_enforced(client):
    Csrf.enforce_in_tests = True
    response = await client.post("/profile", data={"name": "Alice"})
    assert response.status_code == 419
```

## Routes and paths

For named-route URLs:

```python
async def test_get_by_route_name(client):
    user = await UserFactory().create()
    url = Url.route("users.show", user_id=user.id)
    response = await client.get(url)
    assert response.status_code == 200
```

This keeps tests robust to URL-shape refactors.

## Testing redirects

```python
async def test_login_redirects_to_dashboard(client):
    response = await client.post("/login", data={"email": "a@b.com", "password": "..."}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
```

By default the test client follows redirects. Pass `follow_redirects=False` to assert on the redirect itself.

## File uploads

```python
async def test_upload(client):
    with open("tests/fixtures/avatar.png", "rb") as f:
        response = await client.post(
            "/avatar",
            files={"file": ("avatar.png", f, "image/png")},
        )
    assert response.status_code == 201
```

## Streaming responses

```python
async def test_download_csv(client):
    response = await client.get("/users.csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    content = await response.aread()
    rows = content.decode().splitlines()
    assert rows[0] == "id,name"
```

## WebSocket tests

For broadcasting tests, see [Broadcasting](broadcasting.md#testing-broadcasts).

## Where to next?

- [Database tests](database.md) — per-test rollback.
- [Mocking](mocking.md) — fakes for Mail, Bus, Notification, Event.
- [Testing → Getting Started](index.md) — fixtures and project layout.
