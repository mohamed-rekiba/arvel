# Reverb

Reverb is Arvel's first-party WebSocket server, fully compatible with the Pusher protocol (v7). It powers [Broadcasting](broadcasting.md) and runs in-process — no separate Node service required.

## Configuration

```env
REVERB_APP_ID=local
REVERB_APP_KEY=local-key
REVERB_APP_SECRET=local-secret
REVERB_HOST=0.0.0.0
REVERB_PORT=8080
REVERB_ALLOWED_ORIGINS=https://app.example.com
```

By default, Reverb denies all origins. Add the production frontend origins to `REVERB_ALLOWED_ORIGINS` (comma-separated) or set it to `*` to allow any origin (dev only).

## Running the server

```bash
arvel reverb:start
```

The server binds to `REVERB_HOST:REVERB_PORT` and serves the Pusher protocol over WebSocket. It supports public, private, and presence channels (see [Broadcasting](broadcasting.md)).

## Trusted proxies

If Reverb runs behind a reverse proxy (nginx, ALB, Cloudflare), set the trusted proxy list so client IP attribution from `X-Forwarded-For` works correctly:

```env
REVERB_TRUSTED_PROXIES=10.0.0.0/8,192.168.0.0/16
```

The server picks the right-most untrusted hop as the remote address.

## Performance

Reverb runs on a single asyncio event loop and scales vertically. For benchmarks see `benchmarks/bench_reverb.py` in the repository.

## Production deployment

- Place a TLS-terminating proxy in front (nginx, Caddy, ALB)
- Run multiple Reverb processes behind a sticky-session load balancer
- For cross-process broadcasting, set `BROADCASTING_DRIVER=redis` so all Reverb instances publish through a shared Redis backplane

## See also

- [Broadcasting](broadcasting.md) — the application-level API.
- [Redis](redis.md) — the cross-process backplane.
- [Deployment](deployment.md) — running Reverb in production.
