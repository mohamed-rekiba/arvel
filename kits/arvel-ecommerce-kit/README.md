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
  - [`arvel-permission`](https://arvel.dev/packages/permission) — roles and permissions, with route middleware
  - [Mail](https://arvel.dev/features/mail) + [Queues](https://arvel.dev/features/queues) — async jobs, SMTP mail
  - [Scheduler](https://arvel.dev/features/scheduling) — periodic read-model refresh via `arvel schedule:work`
  - [i18n](https://arvel.dev/features/localization) — locale negotiation middleware, JSONB translations
- [PostgreSQL 18](https://www.postgresql.org) — JSONB columns and a materialized catalog view
- [Valkey 9](https://valkey.io) — cache, session store, and queue backend (Redis-protocol-compatible BSD-3 fork; the kit keeps the `redis` service name and `redis://` URLs)
- [Caddy 2](https://caddyserver.com) — single-origin edge for the dev stack (frontend, `/api/*`, and `/media/*` in S3 mode)
- [MinIO](https://min.io) — S3-compatible object store for `arvel-image` uploads (default — see [Storage](#storage-s3-default-local-opt-in))
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

- **Primary entry (Caddy edge)**: http://localhost:8002 — single origin for frontend, `/api/*`, and `/media/*`
- **Interactive API docs**: http://localhost:8002/api/docs
- **Caddy health**: http://localhost:8002/healthz

Caddy fans requests out to the right upstream so the SPA, API, and uploaded
assets share one origin (no CORS). The direct ports stay open for debugging
and for local-mode media:

- **Frontend (raw Vite dev server)**: http://localhost:8000
- **Backend (raw FastAPI; also serves local-mode `/media/*` from disk)**: http://localhost:8001
- **MinIO console**: http://localhost:9001 (`minioadmin` / `minioadmin`)

> The kit defaults to `STORAGE_DEFAULT=s3` so seeded and uploaded media flow
> through MinIO → Caddy and the SPA loads everything from `:8002`. If you flip
> to `STORAGE_DEFAULT=local` (zero-deps fallback), media lives on the backend's
> disk and is served at `:8001/media/<file>` — **load the SPA from `:8001` in
> local mode**, not `:8002`, otherwise Caddy's `/media/*` proxy will look in
> the empty MinIO bucket and return 404. The two drivers can't share `:8002`
> because the framework's local serve and Caddy → MinIO can't both own the
> prefix without one shadowing the other.

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

`docker-compose.yml` defines the full dev stack. The core five always start
with `make up`; MinIO + Caddy come up automatically when Caddy is launched
(it depends on them) or you can start them explicitly with `docker compose up -d caddy`.

| Service | Image | Port (host) | Purpose |
|---|---|---|---|
| `caddy` | `caddy:2.11.4-alpine` | `8002` | Edge reverse proxy — single origin for frontend, `/api/*`, and `/media/*` (active in default s3 mode; dormant for `/media/*` in local mode) |
| `backend` | `python:3.14.5-slim-bookworm` | `8001` | Arvel / FastAPI application |
| `frontend` | `node:24.15.0-alpine3.23` | `8000` | Vite dev server with HMR |
| `scheduler` | `python:3.14.5-slim-bookworm` | — | `arvel schedule:work` for read-model refresh |
| `db` | `postgres:18.4-bookworm` | `5432` | Primary database |
| `redis` | `valkey/valkey:9.1.0-alpine3.23` | `6379` | Cache and queue backend — Valkey (BSD-3, Redis-protocol-compatible) ¹ |
| `minio` | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | `9000`, `9001` | S3-compatible object store (default storage backend) |
| `createbuckets` | `minio/mc:RELEASE.2025-08-13T08-35-41Z` | — | One-shot job — creates the bucket and sets anonymous downloads (`minio/mc` follows its own release cadence; this is its latest tag, not the same date as `minio/minio`) |

¹ The service is named `redis` and `CACHE_URL` still uses the `redis://`
scheme, because `redis://` is the wire-protocol identifier (RESP3) — both
[Redis](https://redis.io) and [Valkey](https://valkey.io) speak it. The image
is Valkey to keep the kit on a BSD-3 licensed cache after Redis adopted the
RSALv2 / SSPL dual license in 2024.

The backend and scheduler bind-mount the entire monorepo and run `uv sync --frozen`, so changes to
any workspace package (`arvel`, `arvel-image`, `arvel-permission`, …) are picked up without a rebuild.

## Common commands

```bash
# Lifecycle
make up              # start everything, then wait until all services are healthy
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
| `STORAGE_DEFAULT` | `s3` | Storage driver: `s3` (default — bundled MinIO + Caddy) or `local` (zero-deps fallback; SPA must load from `:8001`) |
| `ADMIN_SEED_EMAIL` | `admin@example.com` | Admin user created by the seeder |
| `ADMIN_SEED_PASSWORD` | `AdminPwd!1` | Admin password — change before sharing |

<a name="storage-s3-default-local-opt-in"></a>
### Storage (S3 default, local opt-in)

The kit ships `STORAGE_DEFAULT=s3` so the bundled MinIO + Caddy stack works
out of the box. The seeder writes to MinIO, the browser reads through Caddy,
and the SPA stays on a single origin.

What you get out of the box at `:8002`:

- `minio` — S3 server on `minio:9000` (in-network) and the admin console on
  [localhost:9001](http://localhost:9001) (`minioadmin` / `minioadmin`)
- `createbuckets` — one-shot that creates the `arvel-ecommerce-kit` bucket and
  sets anonymous-download so the browser reads assets without signing
- `caddy` — `/media/*` rewrites `http://localhost:8002/media/<key>` →
  `minio:9000/arvel-ecommerce-kit/<key>`, so the SPA loads images from the
  same origin as the API

The default S3 vars in `.env.example` (endpoint, bucket, key, secret, region,
addressing style) are wired to the bundled MinIO. You only need to touch them
when pointing at a real S3 / S3-compatible service. The `minioadmin`
credentials are development-only — rotate `STORAGE_S3_KEY` / `STORAGE_S3_SECRET`
before exposing the instance.

#### Zero-deps fallback (`STORAGE_DEFAULT=local`)

Flip to `local` if you don't want to run MinIO. The framework's local driver
serves `/media/*` from `storage/app/` at `http://localhost:8001/media/<key>`
via its `serve=true` route. Caddy's `/media/*` is wired to MinIO and stays
dormant; the two drivers can't share `:8002` because each would shadow the
other on the same prefix.

**Important**: in local mode, **load the SPA from `:8001`, not `:8002`**.
`STORAGE_LOCAL_URL=/media` is a relative URL — the browser resolves it
against the current origin, so loading from `:8002` makes images request
through Caddy's empty MinIO proxy and 404. The `:8001` direct-backend path
serves both the API and the local-mode media on one origin.

The `/media` prefix is shared across both drivers on purpose — the SPA's
URL shape doesn't change when you flip drivers, only which origin it's
loaded from.

## Deployment

This kit is built for local development and framework testing — it is **not** configured for
production. For a production Arvel app, start from the [Arvel documentation](https://arvel.dev).

## License

MIT — see [LICENSE](../../LICENSE).
