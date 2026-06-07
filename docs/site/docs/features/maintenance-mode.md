# Maintenance Mode

When you're shipping a risky migration or hot-fix, you don't want users hitting a half-deployed app. `arvel down` flips a marker file that the maintenance middleware reads on every request — non-bypass traffic gets `503`, with a clear retry window and (optionally) a branded HTML page. `arvel up` removes the marker and traffic resumes immediately.

## Enabling maintenance mode

`MaintenanceModeMiddleware` ships with the framework. Add it to your ASGI middleware stack (the skeleton already does this in `bootstrap/app.py`):

```python
from arvel.maintenance.middleware import MaintenanceModeMiddleware
from arvel.maintenance.manager import MaintenanceModeManager

app.add_middleware(MaintenanceModeMiddleware, manager=MaintenanceModeManager())
```

The middleware is cheap: it reads the marker file at most once per second per worker (TTL cache), so flipping in and out of maintenance is effectively free.

## Going down

```bash
arvel down                        # bare-bones: random secret, no retry/refresh hints
arvel down --retry 60             # ask clients to wait 60s (Retry-After: 60)
arvel down --refresh 10           # browsers auto-refresh every 10s (Refresh: 10)
arvel down --secret deploy-2026   # use a known bypass secret instead of a random one
arvel down --render storage/framework/maintenance.html
```

The command writes a marker file (`storage/framework/down`) with the configured settings. While that file exists, every request that doesn't carry a matching bypass cookie or `?bypass=<secret>` query string gets a `503` with `Cache-Control: no-store`.

## Bypassing maintenance mode

The bypass secret is the escape hatch for operators and CI checks:

```bash
# Visit the site with the secret query string; the middleware sets a bypass
# cookie and lets you through for the rest of the session.
curl https://app.example.com/?bypass=deploy-2026
```

Subsequent requests just need the cookie (`arvel_bypass`) — no query string required. The cookie's value is checked against the marker's `secret`, so rotating the secret invalidates every existing bypass.

## Custom maintenance page

The default response is plain text, which is fine for an API but ugly for a public web app. Pass `--render` to serve a custom HTML page:

```bash
arvel down --render storage/framework/maintenance.html
```

The path is **read by the middleware on every 503**, so you can tweak the file while the app is down without bouncing workers. If the file goes missing or can't be read, the middleware falls back to plain text and logs an error — the site stays up, just less branded.

The template path is read from the marker file (never from request input), so there's no template-injection vector.

## Coming back up

```bash
arvel up
```

That deletes the marker; the next request through any worker sees no marker and passes through to the app. The TTL cache means it can take up to one second per worker to clear, which is the same tradeoff as going down.

## Scheduler interaction

Scheduled tasks respect maintenance mode by default: while the app is down, the scheduler kernel skips every task with the outcome `in_maintenance_mode`. If a task is essential during downtime (e.g. backups, log rotation), opt it in:

```python
task.in_maintenance_mode = True
```

See [Task Scheduling](scheduling.md) for the scheduling DSL.
