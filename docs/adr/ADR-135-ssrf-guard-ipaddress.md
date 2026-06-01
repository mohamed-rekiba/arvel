# ADR-135: SSRF Guard via stdlib `ipaddress`

**Date**: 2026-05-24
**Status**: Accepted

## Context

`add_media_from_url()` downloads a file from an arbitrary caller-supplied URL. Without a
guard an attacker could supply `http://169.254.169.254/latest/meta-data/` (AWS IMDSv1),
`http://127.0.0.1:5432/`, or similar to exfiltrate internal services.

## Decision

Before opening the httpx connection, resolve the hostname with `socket.getaddrinfo()` and
check each returned IP against Python's `ipaddress` stdlib. Reject addresses where any of the
following holds:

- `ip.is_private`
- `ip.is_loopback`
- `ip.is_link_local`
- `ip.is_multicast`
- `ip.is_reserved`

If any IP in the resolved set is rejected, raise `MediaError("SSRF guard blocked <hostname>")`.

## Alternatives Considered

1. **Block list via regex on the URL** — rejected; easy to bypass with URL encoding or redirects.
2. **`httpx` event hook on connect** — more complex; requires parsing `httpx` internals.
3. **External DNS resolver library** — avoids DNS rebinding but adds a dependency; deferred.

## Limitations

DNS rebinding attacks (time-of-check to time-of-use) can bypass this guard. Documented in
the `add_media_from_url()` docstring. A TOCTOU-safe guard would require connecting through a
controlled proxy or using `httpx` CONNECT-level hooks — deferred to a future security hardening WI.

## Consequences

- **Positive**: Blocks the most common SSRF patterns (metadata services, internal APIs).
- **Positive**: No external dependencies; stdlib only.
- **Negative**: DNS rebinding is still possible; documented limitation.
