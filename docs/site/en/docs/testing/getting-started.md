# Testing Getting Started

If you have shipped a Laravel app before, you already know the rhythm: spin up the app in test mode, hit routes like a browser would, and assert what comes back. Arvel follows that same story—just with async tests, type hints, and Python 3.14+. The testing package lives in `arvel.testing` and wraps familiar pieces (`httpx.AsyncClient` over ASGI, fluent response assertions, database helpers, and fakes for every major subsystem).

This page gets you from zero to a green first test: dependencies, a minimal `pytest` setup, and how `TestClient` fits into the picture.

## What you need

Arvel **0.1.0** targets **Python 3.14+**. For running the framework’s own test suite style, install the project with dev dependencies (pytest, anyio, httpx, coverage tooling, and friends). If you use `uv`, a typical local install looks like this (adjust groups or extras to match your project):

```bash
uv sync --group dev
```

Your `pyproject.toml` can mirror Arvel’s pytest defaults: strict markers, warnings as errors where appropriate, and a sensible timeout so a hung async test does not block CI forever. A minimal `[tool.pytest.ini_options]` might look like this:

```toml
# pyproject.toml (excerpt)
[tool.pytest.ini_options]
testpaths = ["tests"]
minversion = "9.0"
addopts = ["--strict-config", "--strict-markers", "-ra"]
timeout = 30
markers = [
    "db: database-backed tests",
    "integration: tests that touch external services",
]
```

Arvel’s tests use **pytest** with **anyio** so `async def` tests run without extra boilerplate. If your project’s root `conftest.py` auto-marks async tests, you rarely need to decorate every function—check your template.

## TestClient in a nutshell

`TestClient` is an async context manager around **`httpx.AsyncClient`** with **`ASGITransport`**. Every request goes through your FastAPI (Arvel) app’s full middleware stack—sessions, auth, validation, the lot. That is what you want when you are proving behavior, not mocking the framework out from under yourself.

```python
import pytest
from arvel.testing import TestClient

from myapp.main import app  # your FastAPI application instance


@pytest.mark.anyio
async def test_health_returns_ok():
    async with TestClient(app) as client:
        response = await client.get("/health")

    response.assert_ok()
```

`get`, `post`, `put`, `patch`, and `delete` all return a **`TestResponse`**, which wraps `httpx.Response` and adds chainable `assert_*` helpers. You can still access raw response attributes (`status_code`, `json()`, `text`, headers) because `TestResponse` forwards unknown attributes to the underlying response.

## Your first real test

Here is a slightly fuller example: JSON body, status, and a path assertion—similar to how you would chain expectations in Pest or Laravel’s HTTP tests.

```python
import pytest
from arvel.testing import TestClient

from myapp.main import app


@pytest.mark.anyio
async def test_profile_returns_user_name():
    async with TestClient(app) as client:
        response = await client.get("/api/profile/1")

    (
        response
        .assert_status(200)
        .assert_json_path("data.name", "Ada")
        .assert_header("content-type", "application/json")
    )
```

If something fails, the assertion helpers try to include enough of the body and headers in the error message so you are not staring at a bare “AssertionError” with no context.

## Organizing tests

A layout that scales well mirrors your app:

- `tests/conftest.py` — shared fixtures (`app`, `client`, database session, fakes swapped into the container).
- `tests/feature/` — HTTP-level tests with `TestClient`.
- `tests/unit/` — small pieces with fakes and no full ASGI stack when you do not need it.

Mark database tests with `@pytest.mark.db` so you can run `pytest -m "not db"` for a fast slice on a laptop, and the full suite in CI.

## Where to go next

- **HTTP tests** — requests, assertions, and auth context (`acting_as`).
- **Database testing** — transaction rollback, factories, and `DatabaseTestCase`.
- **Fakes** — swap real drivers for in-memory doubles and assert interactions.

Once these pieces click, testing an Arvel app feels less like fighting async and more like the fluent, confident workflow you remember from Laravel—just with `await` where PHP used to hide the event loop.
