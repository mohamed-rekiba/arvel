# arvel-ecommerce-kit

<a name="introduction"></a>
## Introduction

`arvel-ecommerce-kit` is a full-stack e-commerce reference application. Read it to see how Arvel's features fit together in a real app, or scaffold a new project from it.

This is an **example**, not a library you depend on. Use it as a worked example.

<a name="what-it-includes"></a>
## What It Includes

- **Backend** — an Arvel API: storefront, cart, checkout, account, admin CRUD, RBAC, i18n, and media.
- **Frontend** — a Vue 3 SPA (storefront + admin) with an Orval-generated API client.
- **Infra** — Docker Compose with Postgres, Redis, the backend, the frontend dev server, and a scheduler worker.

<a name="scaffolding-from-the-kit"></a>
## Scaffolding From the Kit

The kit doubles as a scaffolding source. It's **not** on PyPI and isn't bundled in the `arvel` wheel — instead it ships as a tarball attached to its own GitHub Release (`arvel-ecommerce-kit-v*`). Just run:

```bash
arvel new my-shop --kit ecommerce
```

The CLI resolves the newest `arvel-ecommerce-kit-v*` release, downloads the tarball (with a progress bar), verifies it against the release's `.sha256` sidecar, caches it under `~/.cache/arvel/kits/`, renames the project to `my-shop`, and runs `uv sync --all-extras --dev`. Inside an Arvel checkout the local workspace copy is used instead, so contributors never hit the network.

Pin a specific version (and skip the release lookup) with `ARVEL_ECOMMERCE_KIT_VERSION`:

```bash
ARVEL_ECOMMERCE_KIT_VERSION=1.0.0 arvel new my-shop --kit ecommerce
```

If the download can't be reached, the command fails with a `KitDownloadError` that points you back at the repo.

<a name="running-the-bundled-app"></a>
## Running the Bundled App

From `kits/arvel-ecommerce-kit/`:

```bash
make env       # copy .env.example to .env
make up        # docker compose up -d db redis backend frontend
make migrate   # arvel migrate (inside the backend container)
make seed      # arvel db:seed
```

Default URLs (from `.env.example`):

- Backend: `http://localhost:8001` — health at `GET /healthz`
- Frontend: `http://localhost:5173`

Run the tests with `make test-backend` and `make test-frontend`.

> [!NOTE]
> `make up` starts Postgres, Redis, the backend, and the frontend. The scheduler service is defined in `docker-compose.yml` but is brought up by `make seed`, not `make up`. Queue (RabbitMQ), mail, and S3 are configured and exercised in the backend tests via testcontainers, but aren't started by the default Compose file.

<a name="where-to-look"></a>
## Where to Look for Each Feature

Use these files as worked examples while reading the rest of the docs:

| Topic | Start here |
|---|---|
| App bootstrap & middleware stack | `backend/bootstrap/app.py` |
| Full route map | `backend/routes/api.py` |
| Provider wiring | `backend/bootstrap/providers.py`, `backend/app/providers/app_service_provider.py` |
| Auth (JWT + refresh cookies + CSRF) | `backend/config/auth.py`, `backend/app/http/controllers/` (auth controller) |
| Roles & permissions | `backend/app/models/user.py`, `backend/config/permission.py`, `backend/app/http/controllers/admin/users.py` |
| Catalog domain & media | `backend/app/models/product.py`, `product_base.py`, `backend/app/services/media_service.py` |
| Cart / checkout | `backend/app/services/cart_service.py`, `order_service.py`, `tests/feature/test_cart_and_checkout.py` |
| Materialized view + refresh | `backend/app/support/products_catalog.py`, `backend/app/console/kernel.py` |
| Observers | `backend/app/observers/` |
| Resources (serialization) | `backend/app/http/resources/` |
| OpenAPI export | `Makefile` (`api-generate` target) |

It pulls in several companion packages — `arvel[permission]` for RBAC and `arvel[image]` for product media — alongside Postgres, Redis, queues, mail, and S3 extras.
