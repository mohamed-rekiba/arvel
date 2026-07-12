# Deployment

An arvel app compiles to a standard ASGI application, so deploying it is deploying an ASGI app —
there's nothing arvel-specific about the hosting. This page covers the moving parts: the server,
the environment, and the release steps.

## The ASGI entrypoint

`asgi.py` exposes your built app as `asgi_app`:

```python
# asgi.py
from bootstrap.app import create_app

asgi_app = create_app().as_asgi()      # a real litestar.Litestar instance
```

Any ASGI server can run it. In development, `arvel serve --reload` wraps
[granian](https://github.com/emmett-framework/granian):

```bash
arvel serve                            # granian, 127.0.0.1:8000
arvel serve --host 0.0.0.0 --port 80   # bind for production
```

In production, run the server directly under a process manager:

```bash
granian --interface asgi asgi:asgi_app --host 0.0.0.0 --port 8000
# or
uvicorn asgi:asgi_app --host 0.0.0.0 --port 8000 --workers 4
```

## Server requirements

- **Python 3.14+**
- Your app's dependencies installed (`uv sync`, or `pip install .` from your built wheel)
- The extras your app uses (`postgres`, `redis`, `s3`, …) present in the deploy environment

## Configuration in production

Set configuration through the environment — never commit `.env`. At minimum:

```bash
APP_ENV=production
APP_DEBUG=false                        # never expose tracebacks/schema in production
APP_KEY=base64:…                       # the real, secret key (generate once, keep stable)
DATABASE_URL=postgresql+asyncpg://…
```

`APP_DEBUG=false` is important: debug mode surfaces error detail meant for developers. See
[Error Handling](errors.md).

A stable `APP_KEY` is what keeps existing encrypted values (cookies, encrypted casts) readable
across deploys — generate it once with `arvel key:generate` and store it as a secret, don't
regenerate per deploy.

## Release steps

A typical release runs migrations before swapping traffic to the new code:

```bash
uv sync --frozen                       # install exactly the locked dependencies
arvel migrate                          # apply outstanding migrations (no prompt — additive)
# restart the server process
```

If you use background work, run the worker and scheduler as their own long-lived processes:

```bash
arvel queue:work                       # process queued jobs (see Queues)
arvel schedule:work                    # tick the scheduler every minute (see Console)
```

For a real cron entry instead of `schedule:work`, call `schedule:run` once a minute:

```
* * * * *  cd /app && arvel schedule:run >> /dev/null 2>&1
```

## Maintenance mode

Take the app offline for a release window without tearing down the server — see
[Configuration](configuration.md#maintenance-mode) for `arvel down` / `arvel up`.

## Optimization

- Serve behind a reverse proxy (nginx/Caddy) for TLS termination and static files.
- Run multiple worker processes (`--workers N`) sized to your CPU; arvel is async, so each worker
  handles many concurrent requests.
- Use a shared cache/session store (Redis/Valkey) so state is consistent across workers — a single
  `.env` change (`SESSION_DRIVER=redis`, `CACHE_DEFAULT=redis`). See [Cache](cache.md).
