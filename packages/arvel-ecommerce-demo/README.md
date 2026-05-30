# Arvel E-Commerce Demo

A full-stack storefront and admin panel that exercises the Arvel framework end-to-end on a real-world domain: multi-vendor product catalog with JSONB i18n fields, materialized storefront reads, RBAC, soft deletes, cart/checkout, media uploads, and a Vue 3 admin SPA.

## Technology Stack and Features

**Backend**

- ⚡ [**Arvel**](https://arvel.dev) — the framework under test
  - 🗄️ [Arvent ORM](https://arvel.dev/arvent) — Models with typed relations, soft deletes, scopes, and QueryBuilder
  - 🔒 [Auth subsystem](https://arvel.dev/authentication) — JWT + session guards, RBAC via `arvel-permission`
  - 📸 [arvel-image](https://arvel.dev/image) — polymorphic media library with Pillow conversions
  - 📋 [arvel-permission](https://arvel.dev/permission) — roles and permissions (Spatie parity)
  - 📬 [Mail](https://arvel.dev/mail) + [Queues](https://arvel.dev/queues) — async background jobs, SMTP mail
  - 🕐 [Scheduler](https://arvel.dev/scheduling) — periodic read-model refresh via `arvel schedule:work`
  - 🌐 [i18n](https://arvel.dev/localization) — locale negotiation middleware, JSONB translations
- 💾 [PostgreSQL 18](https://www.postgresql.org) — primary database with JSONB columns and a materialized catalog view
- ⚡ [Redis](https://redis.io) — cache, session store, and queue backend
- 🐋 [Docker Compose](https://www.docker.com) — one command to start the full stack

**Frontend**

- 🖖 [Vue 3](https://vuejs.org) with `<script setup>` and TypeScript
- 🎨 [Tailwind CSS v4](https://tailwindcss.com) for styling
- 📡 [TanStack Vue Query v5](https://tanstack.com/query) for server-state management
- 🍍 [Pinia](https://pinia.vuejs.org) for client-state (cart, auth)
- 🔁 [Orval](https://orval.dev) — type-safe API client auto-generated from the OpenAPI spec
- 🌍 [vue-i18n](https://vue-i18n.intlify.dev) for front-end translations
- 🧪 [Vitest](https://vitest.dev) + [@vue/test-utils](https://test-utils.vuejs.org) for component tests

**Demo features**

- Storefront: product listing, category browsing, full-text search, product detail, cart, checkout
- Admin SPA: product CRUD, vendor management, user management, order management, roles & permissions
- Image uploads with automatic conversion pipeline (`arvel-image`)
- Multi-vendor catalog with per-vendor product isolation
- JWT authentication with refresh-token rotation
- Email verification and password-reset flows

## Screenshots

### Storefront

| Home | Product Detail | Cart |
|---|---|---|
| Browse products by category with i18n names and materialized pricing | Detail page with image gallery from `arvel-image` | Cart with quantity management and stock validation |

### Admin

| Dashboard | Products | Users & Roles |
|---|---|---|
| Order and revenue overview | Full product CRUD with image upload | Role assignment via `arvel-permission` |

### Interactive API Documentation

Arvel exports the OpenAPI spec via `arvel openapi:export`. Browse the interactive docs at `http://localhost:8001/docs`.

## How To Use It

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

### Quick start

```bash
# Clone the monorepo (or navigate to packages/arvel-ecommerce-demo)
git clone https://github.com/mohamed-rekiba/arvel.git
cd arvel/packages/arvel-ecommerce-demo

# Copy environment file and start services
cp .env.example .env
make up

# Run migrations and seed demo data
make migrate
make seed
```

Open:

- **Storefront**: http://localhost:5173
- **API + built SPA fallback**: http://localhost:8001
- **Interactive API docs**: http://localhost:8001/docs
- **Health check**: http://localhost:8001/healthz

Default admin credentials (from `.env`):

```
ADMIN_SEED_EMAIL=admin@example.com
ADMIN_SEED_PASSWORD=AdminPwd!1
```

Change these before sharing with anyone.

## Docker services

`docker-compose.yml` starts five services:

| Service | Image | Port | Purpose |
|---|---|---|---|
| `backend` | `python:3.14.5-slim-bookworm` | `8001` | Arvel/FastAPI application |
| `frontend` | `node:24.15.0-alpine3.23` | `5173` | Vite dev server with HMR |
| `scheduler` | `python:3.14.5-slim-bookworm` | — | `arvel schedule:work` daemon for read-model refresh |
| `db` | `postgres:18.4-bookworm` | `5432` | Primary database |
| `redis` | `redis:8.6.2-alpine3.23` | `6379` | Cache and queue backend |

The backend and scheduler containers bind-mount the entire monorepo and run `uv sync --frozen`, so local changes to any workspace package (`arvel`, `arvel-image`, `arvel-permission`) are picked up immediately without rebuilding.

## Common Commands

```bash
# Lifecycle
make up              # Start all services and wait for health checks
make down            # Stop services (keep volumes)
make nuke            # Stop services and delete all volumes

# Logs and shell access
make logs            # Follow backend + frontend + scheduler logs
make shell-backend   # Open a shell in the backend container
make shell-frontend  # Open a shell in the frontend container

# Database
make migrate         # Run pending migrations (arvel migrate)
make migrate-fresh   # Drop everything and re-run from scratch
make seed            # Seed roles, catalog, and demo users; restart scheduler

# Frontend
make build-frontend  # Build the Vue app dist served by backend web routes
make api-generate    # Export OpenAPI spec and regenerate the Orval client

# Tests
make test-backend    # pytest tests/unit (inside backend container)
make test-frontend   # Vitest component tests (inside frontend container)
make test            # Both
```

## Backend Development

The backend follows the canonical Arvel project layout:

```
backend/
├── app/
│   ├── http/
│   │   ├── controllers/       # Admin and storefront controllers
│   │   ├── middleware/        # Request middleware
│   │   └── resources/         # API resource serializers
│   ├── models/                # Arvent ORM models
│   ├── providers/             # Service providers
│   └── services/              # Business logic
├── bootstrap/
│   ├── app.py                 # Application factory
│   └── providers.py           # Provider registration
├── config/                    # Typed Pydantic config files
├── database/
│   ├── migrations/            # Alembic-backed Arvel migrations
│   ├── schema/                # Schema DSL files
│   └── seeders/               # Database seeders
├── routes/
│   ├── api.py                 # API routes
│   ├── web.py                 # Web + SPA fallback routes
│   └── console.py             # Console commands
└── public/
    └── asgi.py                # ASGI entrypoint
```

### Running tests

```bash
make test-backend
# or inside the container:
make shell-backend
pytest tests/unit -v
```

Tests use [Testcontainers](https://testcontainers-python.readthedocs.io) to spin up real PostgreSQL and Redis instances — no mocking at the infrastructure layer.

## Frontend Development

The frontend is a Vue 3 + TypeScript SPA. Vite proxies all `/api` requests to the backend container during development.

```
frontend/
├── src/
│   ├── api/           # Orval-generated type-safe API client
│   ├── components/    # Shared UI components
│   ├── layouts/       # Layout wrappers (storefront, admin)
│   ├── pages/         # Route-level page components
│   ├── stores/        # Pinia stores (cart, auth, locale)
│   └── types/         # Shared TypeScript types
├── orval.config.ts    # Orval code-generation config
├── vite.config.ts     # Vite + Tailwind + Vue plugin config
└── vitest.config.ts   # Test config
```

When the backend OpenAPI spec changes, regenerate the client:

```bash
make api-generate
# Equivalent to: arvel openapi:export | orval --config orval.config.ts
```

## Configuration

All configuration lives in `.env`. Copy `.env.example` to get started:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `APP_KEY` | (empty) | HMAC secret for signed URLs — generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DB_URL` | `postgresql+asyncpg://arvel:arvel_local_password@db:5432/arvel_ecommerce` | Database connection string |
| `CACHE_URL` | `redis://...@redis:6379/0` | Redis URL for cache and sessions |
| `STORAGE_DEFAULT` | `local` | Storage driver: `local` or `s3` |
| `ADMIN_SEED_EMAIL` | `admin@example.com` | Admin user created by the seeder |
| `ADMIN_SEED_PASSWORD` | `AdminPwd!1` | Admin password — change before sharing |

### Switching to S3-compatible storage

```env
STORAGE_DEFAULT=s3
STORAGE_S3_ENDPOINT=http://minio:9000
STORAGE_S3_BUCKET=arvel-demo
STORAGE_S3_ACCESS_KEY_ID=minioadmin
STORAGE_S3_SECRET_ACCESS_KEY=minioadmin
STORAGE_S3_REGION=us-east-1
```

## Deployment

This demo is for local development and framework testing. It is not configured for production deployment. For a production Arvel app see the [Arvel deployment docs](https://arvel.dev/deployment).

## License

MIT — see [LICENSE](../../LICENSE).
