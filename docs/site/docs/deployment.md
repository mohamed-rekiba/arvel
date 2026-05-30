# Deployment

When you're ready to deploy your Arvel application, there are a few important things to do to make sure it runs as efficiently as possible. This document covers the basics.

## Server requirements

Arvel needs:

- **Python 3.14+**
- An ASGI server: [Uvicorn](https://www.uvicorn.org/), [Hypercorn](https://hypercorn.readthedocs.io/), or [Granian](https://github.com/emmett-framework/granian).
- A reverse proxy with HTTPS termination (Nginx, Caddy, Traefik, AWS ALB, etc.).
- A database — SQLite for small deployments, Postgres or MySQL for production.
- Redis (optional but recommended for cache, sessions, queue, and broadcasting).

## Server configuration

### Uvicorn

For production, run Uvicorn under a process supervisor (systemd, supervisord, Kubernetes, etc.). Don't use `--reload`.

```bash
uv run uvicorn app:create_app --factory \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --no-access-log
```

Workers ≈ `(2 × CPU cores) + 1` is a reasonable starting point. Tune based on your workload (CPU-bound vs I/O-bound) and observed memory usage.

### Behind a reverse proxy

Have your reverse proxy forward `X-Forwarded-For` and `X-Forwarded-Proto` so Arvel can build correct URLs and detect the original client IP:

=== "Nginx"

    ```nginx
    server {
        listen 443 ssl http2;
        server_name example.com;

        ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host              $host;
            proxy_set_header X-Real-IP         $remote_addr;
            proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    ```

=== "Caddy"

    ```caddyfile
    example.com {
        reverse_proxy 127.0.0.1:8000
    }
    ```

Caddy handles `X-Forwarded-*` and HTTPS automatically.

## Environment configuration

In production, set environment variables directly on the process rather than relying on a committed `.env` file.

### Required variables

```env
APP_ENV=production
APP_DEBUG=false
APP_KEY=<32-byte url-safe random>
DB_URL=postgresql+asyncpg://user:pass@db.internal:5432/myapp
CACHE_DRIVER=redis
SESSION_DRIVER=redis
QUEUE_DRIVER=redis
REDIS_URL=redis://redis.internal:6379/0
```

### Generate an APP_KEY

```bash
uv run arvel key:generate
```

The key encrypts session data and signed URLs. Treat it like a password.

## Build steps

Arvel has no asset build step out of the box. If you're serving HTML with a JS bundle, run your bundler (Vite, esbuild, etc.) as a separate step before deploying.

### Database migrations

Run migrations as part of your deploy pipeline:

```bash
uv run arvel migrate
```

Use `--dry-run` first in a staging environment to confirm the pending set is what you expect.

### Boot-time caches

Run `arvel optimize` at the end of your deploy script to pre-compile config and view caches before traffic hits the new version:

```bash
# Dockerfile CMD or deploy hook
uv run arvel optimize
```

This runs:

- `config:cache` — serializes `config/*.py` module attributes to `bootstrap/cache/config.json` so the next boot skips Python file imports.
- `view:cache` — compiles all Jinja templates to `bootstrap/views/` so the first render skips the parse step.

If you don't use `config/*.py` files (i.e., you rely solely on `@register class MySettings(ArvelSettings)` and environment variables), `config:cache` is a no-op — typed settings always load directly from the environment.

> **Note**: `route:cache` and `event:cache` are not yet available. FastAPI routes include Python callables that can't be serialized to disk.

## Health checks

Arvel ships with two health endpoints:

- `GET /_health/live` — returns 200 as long as the process is running. Use for liveness probes.
- `GET /_health/ready` — returns 200 only when the DB, cache, and queue connections are healthy. Use for readiness probes.

Mount your reverse proxy or orchestrator's health check against `/_health/ready`.

## Queue workers

If you use queues, run one or more dedicated worker processes:

```bash
uv run arvel queue:work --queue=high
```

`queue:work` accepts a single queue name (default `default`) plus `--stop-when-empty` for one-shot mode. Per-job retry and backoff are declared on the `Job` class (`tries`, `backoff`) — see [Queues](queues.md).

Use a process supervisor to keep workers alive. For graceful shutdowns, send `SIGTERM` to each worker process — the worker finishes its current job, then exits cleanly. Your supervisor restarts it with the new code:

```bash
# systemd
systemctl restart arvel-queue-worker

# kubernetes (rolling restart on the worker Deployment)
kubectl rollout restart deploy/arvel-queue-worker
```

`queue:work` installs a `SIGTERM` handler that drains the current job before exiting.

## Schedule runner

If you use the scheduler, run `arvel schedule:work` continuously, or trigger one-shot dispatches from cron every minute:

```bash
* * * * * cd /var/www/myapp && uv run arvel schedule:work --once >> /dev/null 2>&1
```

## Logging

Arvel logs to stdout/stderr by default, in JSON format. Capture them with your container runtime, journald, or a log aggregator.

For production:

```env
LOG_LEVEL=info
LOG_FORMAT=json
```

## Observability

Arvel ships OpenTelemetry hooks for tracing, metrics, and logs. Wire them up to your collector:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.example.com:4317
OTEL_SERVICE_NAME=myapp
```

## Zero-downtime deploys

For zero-downtime deploys with Uvicorn workers:

1. Build the new artifact.
2. Run migrations (forward-compatible only — no destructive changes).
3. Start the new worker pool.
4. Drain the old worker pool (SIGTERM, wait for active requests to finish).

Tools like [Gunicorn](https://docs.gunicorn.org/) and [supervisord](http://supervisord.org/) automate this. Kubernetes does it natively via rolling deploys.

## Containerization

A minimal `Dockerfile`:

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

Multi-stage builds, layer caching, and distroless runtimes are all supported — Arvel doesn't dictate anything past needing Python 3.14+.

## Where to next?

- [Configuration](configuration.md) — env vars and typed config.
- [Cache](cache.md) — production cache drivers.
- [Queues](queues.md) — worker configuration.
