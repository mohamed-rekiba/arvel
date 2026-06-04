# arvel-ecommerce-kit

<a name="introduction"></a>
## Introduction

`arvel-ecommerce-kit` is a full-stack e-commerce reference application. Read it to see how Arvel's features fit together in a real app, or scaffold a new project from it.

This is an **example**, not a library you depend on. Use it as a worked example.

<a name="what-it-includes"></a>
## What It Includes

- **Backend** — an Arvel API: storefront, cart, checkout, account, admin CRUD, RBAC, i18n, and media.
- **Frontend** — a Vue 3 SPA (storefront + admin) with an Orval-generated API client.
- **Infra** — Docker Compose with Postgres, Valkey (Redis-compatible), the backend, the frontend dev server, a scheduler worker, MinIO for S3 uploads (default storage; flip `STORAGE_DEFAULT=local` for a zero-deps fallback), and a Caddy edge that gives the dev stack a single origin.

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

### Prerequisites

Everything runs in containers, so the host only needs:

- **Docker Engine** with the Compose plugin (`docker compose`).
- **GNU Make**.
- **[uv](https://docs.astral.sh/uv/)** — to install and run the Arvel CLI (`uv tool install arvel`) for scaffolding and host-side `arvel` commands.
- Free local ports: `8002` (caddy edge — primary entry), `8001` (backend, debug), `8000` (frontend, debug), `5432` (Postgres), `6379` (Redis-protocol cache, served by Valkey), `9000`/`9001` (MinIO S3 + console). Override them in `.env` if they clash.

### Commands

```bash
make env       # copy .env.example to .env
make up        # start db, redis, backend, frontend, then wait until all are healthy
make migrate   # arvel migrate (inside the backend container)
make seed      # arvel db:seed
```

Default URLs (from `.env.example`):

- **Primary entry (Caddy edge)**: `http://localhost:8002` — single origin for frontend, `/api/*`, and `/media/*` (default `STORAGE_DEFAULT=s3`)
- **API docs**: `http://localhost:8002/api/docs`
- **Caddy health**: `http://localhost:8002/healthz`
- **Backend (raw, debug; also serves local-mode `/media/*` from disk)**: `http://localhost:8001` — health at `GET /healthz`
- **Frontend (raw Vite dev server, debug)**: `http://localhost:8000`
- **MinIO console**: `http://localhost:9001` (`minioadmin` / `minioadmin`)

Caddy proxies the API and the Vite dev server (HMR websocket included), so
the SPA, the API, and S3-mode uploaded assets share one origin and there is
no CORS to set up. Direct host ports stay open for debugging.

> The kit's default driver is `s3`, so `/media/*` resolves through Caddy →
> MinIO. If you flip `STORAGE_DEFAULT=local` (zero-deps fallback), the
> backend serves `/media/*` itself and Caddy's `/media/*` route stays dormant
> — **load the SPA from `:8001` in local mode**, not `:8002`, otherwise
> Caddy will look in the empty MinIO bucket and 404. Local = `:8001`,
> S3 + Caddy = `:8002`. The two drivers can't share `:8002` because each
> would shadow the other on the same prefix.

Run the tests with `make test-backend` and `make test-frontend`.

> [!NOTE]
> `make up` starts Postgres, the cache (Valkey image, exposed as the `redis` service), the backend, and the frontend. Caddy and MinIO come up automatically when something depends on them, or with `docker compose up -d caddy`. The scheduler service is defined in `docker-compose.yml` but is brought up by `make seed`, not `make up`. Queue (RabbitMQ) and mail are configured and exercised in the backend tests via testcontainers, but aren't started by the default Compose file.

### Storage drivers

The kit ships `STORAGE_DEFAULT=s3` so the bundled `minio` + `createbuckets`
+ `caddy` services work out of the box:

- Backend pushes uploads to `minio:9000` (in-network S3 endpoint, signed)
- Browser reads through the Caddy edge — `/media/*` rewrites
  `http://localhost:8002/media/<key>` → `minio:9000/arvel-ecommerce-kit/<key>`
- `createbuckets` one-shot creates the bucket and sets anonymous-download so
  the browser fetches without signed URLs
- MinIO console on [localhost:9001](http://localhost:9001)
  (`minioadmin` / `minioadmin`)

All S3 defaults in `.env.example` (endpoint, bucket, key, secret) are wired
to the bundled MinIO; you only need to override them when pointing at a real
S3 service. Default `minioadmin` credentials are development-only — rotate
`STORAGE_S3_KEY` / `STORAGE_S3_SECRET` before exposing the instance.

#### Zero-deps fallback: `STORAGE_DEFAULT=local`

```bash
# In .env (or environment):
STORAGE_DEFAULT=local
```

Local mode skips MinIO entirely — the framework's local driver serves
`/media/*` from `storage/app/` at the backend's `:8001`. Caddy's `/media/*`
route is wired to MinIO and stays dormant. **Load the SPA from `:8001`**
in this mode, not the Caddy edge at `:8002`, otherwise the relative
`/media/<key>` URLs go to Caddy's empty MinIO proxy and return 404.

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

It pulls in several companion packages — `arvel[permission]` for RBAC and `arvel[image]` for product media — alongside Postgres, the Valkey-backed Redis-protocol cache, queues, mail, and S3 extras.
