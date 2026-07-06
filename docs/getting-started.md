# Getting Started

arvel is an async-first, type-safe Python web framework that ships with the batteries most apps
need — routing, an ORM, validation, views, queues, mail, and more — without making you wire them
together. This page takes you from an empty project to a running app that serves a route, validates
input, renders a view, and has a test. Fifteen minutes, give or take.

By the end you'll have seen the shape of every arvel app: a small core, capabilities you opt into,
and a single application object that ties them together.

## Requirements

arvel targets **Python 3.14+** and is async to the core. We recommend
[uv](https://docs.astral.sh/uv/) for managing dependencies — every example here uses it — but pip
works too.

## Installing

Start with the core, then add what you need:

```bash
uv add arvel                      # the light core — CLI, container, helpers
uv add 'arvel[standard]'          # the usual web stack: http, db, queue, cache, view, mail, image
```

The core is deliberately tiny. Every capability lives behind an **extra** and its heavy engine is
imported *lazily* — so `import arvel` stays fast, and your dependency graph (and cold start) only
carries what you actually use:

```bash
uv add 'arvel[http]'              # serve HTTP            (Litestar)
uv add 'arvel[postgres]'          # the ORM on Postgres   (SQLAlchemy + asyncpg)
uv add 'arvel[queue]'             # background jobs        (taskiq)
uv add 'arvel[view]'              # server-rendered HTML   (Jinja2)
```

Reach for `arvel[standard]` when you just want "a normal web app" and don't want to think about it;
reach for the individual extras when you care about a lean install. Each capability's page lists the
extra it needs.

## The shape of an app

Everything hangs off one **application** object. You configure it once — its config, the providers
that register capabilities — and from then on it's what serves requests, runs jobs, and resolves
dependencies:

```python
# bootstrap.py
from arvel import Application

def create_app():
    return (
        Application.configure(base_path=".")
        .with_config(CONFIG)
        .with_providers([...])        # the capabilities your app uses
        .create()
    )
```

You'll rarely touch the internals — but it helps to know that a request, a queued job, and a CLI
command all run against this same booted application. (More on how that works in
[Architecture Concepts](architecture.md).)

## Your first route

Routes map a URL to a handler — an `async` function that returns data. Return a dict and arvel sends
JSON:

```python
# app/routes.py
from arvel import Route

async def hello(request):
    return {"message": "Hello, arvel"}

Route.get("/", hello, name="home")
```

Naming a route (`name="home"`) lets you generate URLs to it later instead of hardcoding paths — see
[Routing](routing.md) for path parameters, route groups, and middleware.

## Serving it

Your app compiles down to a standard ASGI application, so any ASGI server can run it:

```python
# asgi.py
from bootstrap import create_app

app = create_app().as_asgi()      # a real litestar.Litestar instance
```

```bash
uvicorn asgi:app --reload
```

`as_asgi()` is where arvel's dynamic routes are adapted onto [Litestar](https://litestar.dev) — you
write the ergonomic API, and you still get a real, inspectable ASGI app (OpenAPI included).

## Validating input

Never trust what comes in. Describe the rules and let arvel enforce them; on failure it raises a
`422` with a per-field error map, which the framework renders for you:

```python
from arvel.validation import Validator

data = await request.json()
clean = Validator(data, {
    "email": "required|email",
    "age":   "nullable|integer|min:18",
}).validate()                     # -> the validated data, or a 422 on bad input
```

Rules are just `|`-delimited strings. There's a lot more — custom rules, typed form objects,
localized messages — in [Validation](validation.md).

For ad-hoc reads without a schema, the request exposes convenience accessors: `await
request.input("key")` (JSON body first, then query string), `await request.boolean("flag")` (coerces
`"1"/"true"/"on"/"yes"`), and `request.bearer_token()` (the token from an `Authorization: Bearer`
header) — alongside the raw `request.json()` / `request.query(...)` / `request.header(...)`.

## Rendering a view

For server-rendered HTML, return a view. arvel renders it through Jinja2 and turns it into a
response:

```python
from arvel import view

async def welcome(request):
    return await view("welcome", {"user": request.user()}).to_response()
```

```html
<!-- resources/views/welcome.html -->
{% extends "layouts/app.html" %}
{% block content %}<h1>Hello {{ user.name }}</h1>{% endblock %}
```

## Writing a test

arvel ships a test kit so you can exercise your app like a real client and assert on side effects
without hitting real services:

```python
from arvel.testing import client, fake
from arvel import Mail

def test_homepage():
    with client(create_app().as_asgi()) as http:
        assert http.get("/").status_code == 200

async def test_welcome_email_sent():
    mail = fake(Mail)                 # swap the mailer for a spy
    await register(user)
    mail.assert_sent(WelcomeMail)     # ...and assert what would have been sent
```

`fake(...)` replaces a service (mail, queue, storage, …) with an in-memory double for the test, so
you assert on intent rather than waiting on the network. See [Testing](testing.md) for the full kit.

## Where to go next

You've now touched routing, validation, views, and testing. From here:

- **[Architecture Concepts](architecture.md)** — how arvel stays light, type-safe, and faithful to
  its engines; the application lifecycle in full.
- **[Routing](routing.md)** and **[Database & ORM](database/index.md)** — the two you'll live in most.
- **[The Service Container](container.md)** — how dependencies are wired, and why `fake()` works.

Each capability has its own page under **The Basics** and **Digging Deeper** — and every one opens
with the problem it solves before the API, so you can read them in any order.
