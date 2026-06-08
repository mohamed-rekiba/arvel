# WI-arvel-051 — TrustProxies (general request-path)

- **Module:** 51 (HTTP — request path)
- **Complexity:** L2
- **Risk tier:** 3 (security path)
- **Data classification:** confidential
- **Status:** completed

A WI-043 bucket-3 feature gap, split out of WI-050. Trusted-proxy resolution of
`X-Forwarded-*` existed for the infra endpoints (`/_health`, `/_metrics` via
`observability/forwarded.py`) and the reverb websocket server, but **not** the
general HTTP request path. Behind a load balancer that means:

- `Throttle._default_key` keys on `request.client.host` → every request buckets
  into the proxy's IP (one client can drain everyone's quota; an abuser can't be
  isolated).
- Signed-URL validation, redirects, and `URL` generation read
  `request.url.scheme` / host → behind a TLS-terminating proxy the app sees
  `http` and the internal host.
- Request logs record the proxy IP.

This is Laravel's `TrustProxies` (Symfony `Request::setTrustedProxies`).

## What landed

### `TrustProxiesMiddleware`

`http/middleware/trust_proxies.py` — pure ASGI, mounted as the **outermost**
layer so every downstream middleware and handler sees a corrected scope. When
the TCP peer matches a trusted proxy it rewrites:

- `scope["client"]` → `(resolved_client_ip, original_port)`
- `scope["scheme"]` → from `X-Forwarded-Proto` (`http`/`https`; mapped to
  `ws`/`wss` for websocket scopes)
- the `host` header → from `X-Forwarded-Host`

Client-IP selection reuses `observability/forwarded.resolve_client_ip`
(right-to-left, skip trusted hops). For `*` (trust all) every hop is trusted, so
the original client is the **leftmost** XFF entry — handled with a dedicated
branch since `resolve_client_ip` would return the peer there.

### `HttpConfig.trusted_proxies`

`http/config.py` — read from the bare `TRUSTED_PROXIES` env var (Laravel name,
via `NoPrefix`), CSV-parsed. `*` trusts every peer (expands to `0.0.0.0/0` +
`::/0`). Bound in `HttpServiceProvider`; the middleware is mounted only when the
list is non-empty.

## Design notes

- **Default off = fail-safe.** Empty `TRUSTED_PROXIES` (the default) → the
  middleware isn't mounted and forwarded headers are ignored (the peer is the
  client). Apps not behind a proxy see no behavior change.
- **Peer-trust gate.** `X-Forwarded-*` is client-controlled, so it's honored
  only when the TCP peer is in a trusted CIDR — a spoofed header from an
  untrusted peer is ignored.
- **`*` is documented as risky.** Only safe when the LB is the sole ingress and
  the app port is firewalled off from direct access.
- **Scope kept tight.** No separate `X-Forwarded-Port` scope key (rare;
  `X-Forwarded-Host` may carry `host:port`), no per-header trust bitmask.

## Tests

`packages/arvel/tests/http/middleware/test_trust_proxies.py` (14 cases):
untrusted peer leaves the scope untouched; trusted peer resolves the client IP
(right-to-left), scheme, and host; `*` picks the leftmost XFF entry; no-XFF keeps
the peer; invalid proto ignored; lifespan passthrough; websocket `https`→`wss`;
package + module import identity; `TRUSTED_PROXIES` CSV parse + empty default.

## Gates

ruff check clean; `uv run mypy` 0 issues (450 files); `uv run pyright` 0/0; http
+ application + auth + test_auth suites pass; mkdocs build --strict clean. Also
fixed a latent WI-050 re-export: `arvel.http.middleware` imported
`CsrfMismatchException` through `_middleware_core` (not in its `__all__`); now
imported from the canonical `arvel.http.exceptions`.
