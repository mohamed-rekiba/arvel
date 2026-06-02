# Arvel E-Commerce Kit

A full-stack storefront and admin panel that exercises the [Arvel](https://arvel.dev) framework
end-to-end on a realistic domain: a multi-vendor product catalog with JSONB i18n fields, a
materialized read model, RBAC, soft deletes, cart and checkout, media uploads, and a Vue 3 admin SPA.

This is a reference app, not a starter template. It exists to prove the framework works on something
non-trivial and to show how the pieces fit together.

## Stack

**Backend**

- [**Arvel**](https://arvel.dev) — the framework under test
  - [Arvent ORM](https://arvel.dev/orm/models) — typed relations, soft deletes, scopes, query builder
  - [Auth](https://arvel.dev/features/authentication) — JWT + session guards, RBAC via `arvel-permission`
  - [`arvel-image`](https://arvel.dev/packages/image) — polymorphic media library with Pillow conversions
  - [`arvel-permission`](https://arvel.dev/packages/permission) — roles and permissions (Spatie parity)
  - [Mail](https://arvel.dev/features/mail) + [Queues](https://arvel.dev/features/queues) — async jobs, SMTP mail
  - [Scheduler](https://arvel.dev/features/scheduling) — periodic read-model refresh via `arvel schedule:work`
  - [i18n](https://arvel.dev/features/localization) — locale negotiation middleware, JSONB translations
- [PostgreSQL 18](https://www.postgresql.org) — JSONB columns and a materialized catalog view
- [Redis](https://redis.io) — cache, session store, and queue backend
- [Docker Compose](https://docs.docker.com/compose/) — one command to bring up the full stack

**Frontend**

- [Vue 3](https://vuejs.org) with `<script setup>` and TypeScript
- [Tailwind CSS v4](https://tailwindcss.com) for styling
- [TanStack Vue Query v5](https://tanstack.com/query) for server state
- [Pinia](https://pinia.vuejs.org) for client state (cart, auth)
- [Orval](https://orval.dev) — type-safe API client generated from the OpenAPI spec
- [vue-i18n](https://vue-i18n.intlify.dev) for front-end translations
- [Vitest](https://vitest.dev) + [@vue/test-utils](https://test-utils.vuejs.org) for component tests

## Quick start

You need [Docker](https://docs.docker.com/get-docker/) and Docker Compose. Nothing else is installed
on the host — the backend and scheduler containers `uv sync` the workspace on first boot.

```bash
git clone https://github.com/mohamed-rekiba/arvel.git
cd arvel/kits/arvel-ecommerce-kit

make up        # copies .env from .env.example, starts services, waits for health
make migrate   # run pending migrations
make seed      # seed roles, catalog, and sample users
```

Then open:

- **Storefront (Vite dev server)**: http://localhost:8000
- **API + built SPA fallback**: http://localhost:8001
- **Interactive API docs**: http://localhost:8001/docs
- **Health check**: http://localhost:8001/healthz

Default admin credentials come from `.env`:

```
ADMIN_SEED_EMAIL=admin@example.com
ADMIN_SEED_PASSWORD=AdminPwd!1
```

Change these before sharing the instance with anyone.

## Scaffold your own project

To start a new project *from* this kit rather than running the reference app in place,
use the Arvel CLI — it downloads the kit and renames it to your project:

```bash
uv tool install arvel
arvel new my-store --kit ecommerce
cd my-store
```

The kit isn't on PyPI. `arvel new` fetches the latest `arvel-ecommerce-kit` release
tarball from GitHub, verifies its checksum, and scaffolds it under your project name.

## Services

`docker-compose.yml` starts five services:

| Service | Image | Port | Purpose |
|---|---|---|---|
| `backend` | `python:3.14.5-slim-bookworm` | `8001` | Arvel / FastAPI application |
| `frontend` | `node:24.15.0-alpine3.23` | `8000` | Vite dev server with HMR |
| `scheduler` | `python:3.14.5-slim-bookworm` | — | `arvel schedule:work` for read-model refresh |
| `db` | `postgres:18.4-bookworm` | `5432` | Primary database |
| `redis` | `redis:8.6.2-alpine3.23` | `6379` | Cache and queue backend |

The backend and scheduler bind-mount the entire monorepo and run `uv sync --frozen`, so changes to
any workspace package (`arvel`, `arvel-image`, `arvel-permission`, …) are picked up without a rebuild.

## Common commands

```bash
# Lifecycle
make up              # start everything, then wait until all services are healthy
make healthcheck          # wait until db, redis, backend, frontend are healthy
make down            # stop services (keep volumes)
make nuke            # stop services and delete all volumes
make ps              # list running services

# Logs and shells
make logs            # follow backend + frontend + scheduler logs
make shell-backend   # shell into the backend container
make shell-frontend  # shell into the frontend container

# Database
make migrate         # run pending migrations
make migrate-fresh   # drop everything and re-run from scratch
make seed            # seed roles, catalog, and sample users

# Frontend
make build-frontend  # build the Vue app served by the backend web routes
make api-generate    # export the OpenAPI spec and regenerate the Orval client

# Tests
make test-backend    # pytest (inside the backend container)
make test-frontend   # Vitest component tests (inside the frontend container)
make test            # both
```

## Layout

The backend follows the canonical Arvel project layout:

```
backend/
├── app/
│   ├── http/
│   │   ├── controllers/    # admin + storefront controllers
│   │   ├── middleware/      # request middleware
│   │   └── resources/       # API resource serializers
│   ├── models/              # Arvent ORM models
│   ├── providers/           # service providers
│   └── services/            # business logic
├── bootstrap/
│   ├── app.py               # application factory
│   └── providers.py         # provider registration
├── config/                  # typed Pydantic config
├── database/
│   ├── migrations/          # Alembic-backed Arvel migrations
│   ├── schema/              # schema DSL files
│   └── seeders/             # database seeders
├── routes/
│   ├── api.py               # API routes
│   ├── web.py               # web + SPA fallback routes
│   └── console.py           # console commands
└── public/
    └── asgi.py              # ASGI entrypoint

frontend/
├── src/
│   ├── api/                 # Orval-generated API client
│   ├── components/          # shared UI components
│   ├── layouts/             # storefront + admin layouts
│   ├── pages/               # route-level pages
│   ├── stores/              # Pinia stores (cart, auth, locale)
│   └── types/               # shared TypeScript types
├── orval.config.ts
├── vite.config.ts
└── vitest.config.ts
```

When the backend OpenAPI spec changes, regenerate the client with `make api-generate`.

Backend tests use [Testcontainers](https://testcontainers-python.readthedocs.io) to spin up real
PostgreSQL and Redis — no mocking at the infrastructure layer.

## Configuration

All configuration lives in `.env` (copied from `.env.example` by `make up`). Key variables:

| Variable | Default | Description |
|---|---|---|
| `APP_KEY` | (empty) | HMAC/encryption secret — generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DB_URL` | `postgresql+asyncpg://arvel:...@db:5432/arvel_ecommerce` | Database connection string |
| `CACHE_URL` | `redis://...@redis:6379/0` | Redis URL for cache and sessions |
| `STORAGE_DEFAULT` | `local` | Storage driver: `local` or `s3` |
| `ADMIN_SEED_EMAIL` | `admin@example.com` | Admin user created by the seeder |
| `ADMIN_SEED_PASSWORD` | `AdminPwd!1` | Admin password — change before sharing |

### S3-compatible storage

```env
STORAGE_DEFAULT=s3
STORAGE_S3_ENDPOINT=http://minio:9000
STORAGE_S3_BUCKET=arvel-ecommerce-kit
STORAGE_S3_ACCESS_KEY_ID=minioadmin
STORAGE_S3_SECRET_ACCESS_KEY=minioadmin
STORAGE_S3_REGION=us-east-1
```

## Deployment

This kit is built for local development and framework testing — it is **not** configured for
production. For a production Arvel app, start from the [Arvel documentation](https://arvel.dev).

## License

MIT — see [LICENSE](../../LICENSE).
