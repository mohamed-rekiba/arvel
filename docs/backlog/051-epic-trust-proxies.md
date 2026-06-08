# Epic: TrustProxies (general request-path)

## Summary
Honor `X-Forwarded-*` on the general HTTP request path when the TCP peer is a
trusted proxy, so behind a load balancer `request.client.host` (and the throttle
key that reads it), the scheme, and the host reflect the real client. WI-043
bucket-3 gap, split out of WI-050 (security path).

**Spec:** `docs/pipeline/specs/WI-arvel-051-trust-proxies.md`

## Delivered

### Story 1: TrustProxiesMiddleware — Done
Pure-ASGI `TrustProxiesMiddleware` (`http/middleware/trust_proxies.py`) mounted as
the outermost layer. When the peer matches a trusted proxy it rewrites the scope:
client IP from `X-Forwarded-For` (reusing `observability/forwarded.resolve_client_ip`;
leftmost entry for `*`), scheme from `X-Forwarded-Proto` (ws/wss for websockets),
host from `X-Forwarded-Host`. Untrusted peer → scope untouched.

### Story 2: HttpConfig.trusted_proxies — Done
New `HttpConfig` (`http/config.py`) reads the bare `TRUSTED_PROXIES` env var
(CSV of IPs/CIDRs; `*` trusts all). Bound in `HttpServiceProvider`; the middleware
mounts only when the list is non-empty (default off = fail-safe).

## Security
Forwarded headers are client-controlled, so they're honored only behind a trusted
peer. Default empty → ignored entirely. `*` documented as safe only when the LB is
the sole ingress and the app port is firewalled.

## Tests
`tests/http/middleware/test_trust_proxies.py` (14 cases).

## Gates
ruff clean; mypy 0 (450 files); pyright 0/0; http + application + auth + test_auth
suites pass; mkdocs --strict clean.
