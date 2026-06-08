# Epic: Infra-endpoint CIDR guards bypassable via spoofed X-Forwarded-For

## Summary
`/_metrics` and `/_health` restrict access by CIDR, but resolved the client IP from
the first `X-Forwarded-For` value unconditionally. Since that header is
client-controlled, anyone could send `X-Forwarded-For: 127.0.0.1` (or an
allowlisted IP) to defeat the guard and read internal telemetry / health detail.
The framework already had the correct trusted-proxy model in reverb; these two
endpoints now follow it.

**Module:** observability + health · **Spec:** `docs/pipeline/specs/WI-arvel-030-forwarded-ip-guard-bypass.md`

## Stories

### Story 1: Forwarded headers can't spoof the metrics/health guard
**As an** operator who restricts `/_metrics` or `/_health` by CIDR, **I want** the
guard to use the real connection source, **so that** an attacker can't bypass it by
sending a forged `X-Forwarded-For` header.

**Acceptance Criteria**:
- [ ] A request with `X-Forwarded-For` claiming an allowlisted IP, from an untrusted peer, is rejected (403).
- [ ] The CIDR check uses the TCP peer IP by default.
- [ ] `/_health` remains open when no allowlist is configured.

**Security Requirements**:
- [ ] `X-Forwarded-For` is honored only when the TCP peer is a configured trusted proxy (A01 broken access control).
- [ ] No internal telemetry or health/exception detail is reachable past the guard via header spoofing (A09/A10).

### Story 2: Trusted-proxy deployments still work
**As an** operator running behind a load balancer, **I want** to declare trusted
proxies, **so that** the guard evaluates the real client from `X-Forwarded-For`.

**Acceptance Criteria**:
- [ ] `OBSERVABILITY_TRUSTED_PROXIES` (and the `trusted_proxies` route param) enable right-most-untrusted-hop XFF resolution.
- [ ] When all hops are trusted, the resolver falls back to the peer.

**Requirement Refs**: C1 (XFF spoof bypass), C2 (trusted-proxy resolution)
**Priority**: Must · **Complexity**: Small · **Status**: Done
