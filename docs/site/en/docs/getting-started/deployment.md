# Deployment

Shipping an Arvel app is mostly the same story as shipping any well-behaved ASGI service: run **uvicorn** (or another ASGI server) with multiple workers in production, put configuration in the environment, and let a reverse proxy handle TLS and buffering. Arvel does not invent a separate deployment runtime—it gives you FastAPI and Starlette under the hood, plus a CLI for local ergonomics. This page covers production uvicorn, a practical Docker shape, and the environment variables you should treat as non-negotiable outside development.

## Running with uvicorn in production

`arvel serve` is optimized for **local development** (reload, single-process defaults). In production, call **uvicorn** directly so you control workers, logging, and process management.

From the project root:

```bash
uvicorn bootstrap.app:create_app --factory --host 0.0.0.0 --port 8000 --workers 4
```

Guidelines that tend to age well:

- **Disable reload**—it is for development only.
- **Set workers** based on CPU cores (often `2 × cores + 1` as a starting point for CPU-bound sync work; profile your own workload).
- **Terminate TLS at your load balancer or ingress**, not necessarily inside the Python process, unless you have a specific reason to end-to-end encrypt inside the cluster.

If the app sits behind nginx, Caddy, or another proxy, enable forwarded headers so Starlette knows the external scheme and client IP. When you used `arvel serve`, `--proxy-headers` did that; with raw uvicorn, configure your proxy and ASGI stack consistently (for example trusted proxies / forwarded allow lists) so redirects and absolute URLs stay correct.

## Docker deployment

A minimal **Dockerfile** keeps dependencies reproducible and runs uvicorn as the container command. Adjust the Python base image tag to match what your security policy allows; the important part is installing your project (often with `uv sync --frozen`) and invoking the same ASGI target as production.

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Copy project metadata first for better layer caching
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

COPY . .

ENV APP_ENV=production
EXPOSE 8000

CMD ["uvicorn", "bootstrap.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

Build and run:

```bash
docker build -t my-arvel-app .
docker run --rm -p 8000:8000 --env-file .env.production my-arvel-app
```

Mount secrets with your orchestrator’s mechanism (Kubernetes secrets, ECS task definitions, etc.) rather than baking them into the image.

## Environment configuration for production

Production should look **explicitly different** from your laptop:

```bash
APP_ENV=production
APP_DEBUG=false
APP_KEY=<long-random-secret>
DB_URL=postgresql+asyncpg://...
CACHE_DRIVER=redis
CACHE_REDIS_URL=redis://redis:6379/0
```

Checklist:

- **Never enable `APP_DEBUG` in production**—it affects error surfaces and tooling you do not want exposed to end users.
- **Rotate `APP_KEY`** when compromised; anything derived from it (sessions, signed URLs) must be invalidated consciously.
- **Use real database and cache URLs** from managed services; keep usernames and passwords in a secret store.
- **Tune pool settings** (`DB_POOL_SIZE`, etc.) to match your provider’s connection limits.

Arvel’s Pydantic settings layer means the same code paths read these values in staging and production—what changes is only the data you inject at runtime.

You are ready to run behind uvicorn, package in Docker, and configure like a twelve-factor app. For local setup details, revisit [Installation](installation.md) and [Configuration](configuration.md).
