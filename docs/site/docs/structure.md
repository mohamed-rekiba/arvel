# Directory Structure

Arvel applications follow a convention-driven layout. When you scaffold a new project with `arvel new`, you get this:

```
my-app/
├── app/                  # your application code (you own this)
│   ├── __init__.py
│   ├── bootstrap/        # Application factory, providers, config classes
│   ├── http/             # controllers, middleware, form requests, resources
│   ├── models/           # Arvent models
│   ├── policies/         # authorization policies
│   ├── jobs/             # queueable jobs
│   ├── events/           # event classes
│   ├── listeners/        # event listeners
│   ├── mail/             # Mailable classes
│   ├── notifications/    # Notification classes
│   ├── providers/        # ServiceProvider subclasses
│   └── routes/           # route definitions (web.py, api.py, channels.py)
├── config/               # typed config files (Pydantic Settings)
├── database/
│   ├── migrations/       # Alembic migrations
│   ├── seeders/          # Seeder classes
│   └── factories/        # model factories
├── resources/
│   ├── views/            # Jinja2 templates (if you serve HTML)
│   └── lang/             # i18n strings (future)
├── routes/               # alternative top-level routes (optional)
├── storage/
│   ├── app/              # user-uploaded files
│   ├── cache/            # filesystem cache
│   ├── logs/             # log files
│   └── framework/        # framework-internal state
├── tests/
│   ├── unit/             # unit tests
│   ├── feature/          # HTTP / end-to-end tests
│   └── conftest.py       # shared fixtures
├── .env.example          # documented environment variables
├── pyproject.toml
└── README.md
```

You're not required to use this layout — Arvel works wherever your code lives. But the convention makes it easier for collaborators (and AI agents) to find things.

## The `app/` directory

This is where your application's heart lives. Most of your custom code goes here.

### `app/bootstrap/`

Contains the `Application` factory. The canonical entrypoint looks like:

```python
# app/bootstrap/app.py
from pathlib import Path
from arvel import Application

app = (
    Application.configure(Path(__file__).resolve().parents[2]).with_environment_from_env().create()
)
```

### `app/http/`

Controllers, middleware, form requests, and API resources. Subdirectories are by feature:

```
app/http/
├── controllers/
│   ├── user_controller.py
│   └── order_controller.py
├── middleware/
│   ├── authenticate.py
│   └── throttle.py
├── requests/
│   ├── store_user.py
│   └── update_user.py
└── resources/
    └── user_resource.py
```

### `app/models/`

Arvent models — one file per model, named after the model.

### `app/policies/`

Authorization policies. Each policy declares which actions a user can perform on a model:

```python
class UserPolicy(Policy):
    def view(self, user: User, target: User) -> bool:
        return user.id == target.id or user.is_admin
```

### `app/jobs/`

Queueable background jobs. Subclass `arvel.queue.Job` and implement `async def handle(self) -> None`.

### `app/events/` and `app/listeners/`

Event-driven side effects. An event is a Pydantic model; listeners are functions or classes that react to events.

### `app/mail/`

Mailable classes (subclasses of `arvel.mail.Mailable`). Each Mailable renders an email body and metadata, then `Mail.to(...).send(...)` ships it through the configured driver.

### `app/notifications/`

Multi-channel notifications. A Notification can target mail, database, broadcast, or a custom channel from a single class.

### `app/providers/`

Custom service providers — where you register your app's bindings, listeners, and gates.

### `app/routes/`

Route definitions. `web.py` for browser routes, `api.py` for JSON routes, `channels.py` for broadcast channels.

## The `config/` directory

Each file in `config/` defines one or more `ArvelSettings` subclasses. The files don't have to follow a naming convention — Arvel auto-discovers anything marked with `@register`.

## The `database/` directory

```
database/
├── migrations/
│   ├── 20260101000001_create_users_table.py
│   └── 20260102000001_create_posts_table.py
├── seeders/
│   └── database_seeder.py
└── factories/
    └── user_factory.py
```

## The `storage/` directory

Runtime state. Should be writable by your app process. Add it to `.gitignore` except for the structural directories:

```gitignore
storage/app/*
!storage/app/.gitkeep
storage/cache/*
!storage/cache/.gitkeep
storage/logs/*
!storage/logs/.gitkeep
```

## The `tests/` directory

Pytest test layout. We recommend:

- `tests/unit/` — fast tests with no I/O.
- `tests/feature/` — HTTP, queue, mail, broadcasting tests using Arvel's testing helpers.
- `tests/conftest.py` — shared fixtures.

## Customizing the layout

Every directory above is a default, not a requirement. If you'd rather use `src/myapp/`, put your config under `settings/`, or skip `resources/` entirely — go ahead. Most Arvel facades resolve through the container; only a few features (auto-discovery of providers, route registration via filesystem) make assumptions about layout, and those can be overridden in `app/bootstrap/app.py`.
