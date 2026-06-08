# WI-arvel-030 — /_health and /_metrics CIDR guards are bypassable via spoofed X-Forwarded-For

- **Module**: 30 — observability (`/_metrics`) + bootstrap health (`/_health`)
- **Complexity**: L2
- **Risk tier**: 3 (A01 broken access control via spoofable header; A09/A10 info exposure)
- **Data classification**: confidential
- **Status**: completed

## Problem

Both `add_metrics_route` and `add_health_route` restrict access by CIDR, but their
`_client_ip` helpers read the **first** `X-Forwarded-For` value unconditionally:

```python
forwarded = request.headers.get("X-Forwarded-For")
if forwarded:
    return forwarded.split(",")[0].strip()
```

`X-Forwarded-For` is client-controlled. Any external caller can send
`X-Forwarded-For: 127.0.0.1` (metrics default allowlist is loopback-only) or an IP
inside `HEALTH_ALLOWED_CIDRS` and pass the guard:

- `/_metrics` → exposes internal Prometheus telemetry (paths, latencies, counts).
- `/_health` → exposes per-service status and exception detail strings
  (`HealthResult(unhealthy, str(exc))`) and component topology.

The guard is the only protection, so the spoof fully defeats it. Worse for health:
the bypass is silent — an operator who sets `HEALTH_ALLOWED_CIDRS` believes the
endpoint is locked down while it isn't.

The framework already solved this for reverb (`resolve_remote_ip`, MEDIUM-3): never
trust forwarded headers unless the TCP peer is a configured trusted proxy. The two
HTTP infra endpoints just didn't follow that model.

## Repro

`add_metrics_route(app, allowed_cidrs=["203.0.113.0/24"])` (peer is loopback), then
`GET /_metrics` with `X-Forwarded-For: 203.0.113.9` → **200** (should be 403).

## Fix

Shared, fail-safe resolver in `arvel/observability/forwarded.py`:

```python
def resolve_client_ip(*, peer_ip, forwarded_for, trusted_proxies) -> str:
    if not trusted_proxies or not forwarded_for or not ip_in_cidrs(peer_ip, trusted_proxies):
        return peer_ip
    for hop in reversed([h for h in forwarded_for.split(",") if h.strip()]):
        if not ip_in_cidrs(hop, trusted_proxies):
            return hop
    return peer_ip
```

- Both routes resolve the client IP via the TCP peer; XFF honored only when the
  peer is in `trusted_proxies` (right-most-untrusted hop), matching reverb.
- New `ObservabilityConfig.trusted_proxies` (`OBSERVABILITY_TRUSTED_PROXIES`,
  default `[]`); `add_health_route`/`add_metrics_route` gain a `trusted_proxies`
  parameter; `Application._add_health_route` threads it from config.
- `throttle_login` reviewed — already keys on the real `scope["client"]` peer, never
  XFF; no change.

## Acceptance criteria

- Spoofed XFF without a trusted proxy never bypasses either CIDR guard.
- With the peer declared trusted, XFF resolves the real client and the guard applies
  to it.
- Health stays open when `allowed_cidrs` is empty (LB/k8s probes).
- ruff + format, mypy, pyright clean; observability + health suites green.

## Out of scope (reviewed, no change)

- `check_and_log_slow_query` caps SQL at 500 chars; queries are parameterized so no
  literal PII in the text.
- `throttle_login` peer keying is correct.

## Files

- `packages/arvel/src/arvel/observability/forwarded.py` (new)
- `packages/arvel/src/arvel/observability/metrics_route.py`
- `packages/arvel/src/arvel/observability/config.py`
- `packages/arvel/src/arvel/health.py`
- `packages/arvel/src/arvel/application/application.py`
- `packages/arvel/tests/observability/test_forwarded_ip.py` (new)
- `packages/arvel/tests/observability/test_metrics_route.py`
- `packages/arvel/tests/services/test_health_endpoint.py`
