# ADR-110: Channel-Auth HMAC-SHA256 Signature Scheme

**Status**: Accepted
**Date**: 2026-05-18

## Context

Private and presence channels require server-side authorization. The client receives an opaque token from `POST /broadcasting/auth` and includes it in `pusher:subscribe`. The Reverb server validates the token against the receiving socket's `socket_id`. Three options for the token scheme:

- **A**: HMAC-SHA256 over `socket_id:channel_name` (private) / `socket_id:channel_name:channel_data_json` (presence). Pusher v7 server-library spec.
- **B**: JWT signed with HS256 / RS256 containing `socket_id` and `channel_name` claims. Modern but heavier and incompatible with `pusher-js`.
- **C**: Random opaque token stored in Redis with TTL, server-side lookup on subscribe. Heavier per-subscribe cost; needs cache invalidation.

## Decision

**Option A** — HMAC-SHA256 per the Pusher v7 spec.

Signature input:
- Private: `<socket_id>:<channel_name>`
- Presence: `<socket_id>:<channel_name>:<channel_data_json>`

Algorithm: HMAC-SHA256.
Output: lowercase hex digest.
Wire format: `<app_key>:<hex_digest>`.

Verification uses `hmac.compare_digest` (constant-time) against a server-recomputed signature with its own secret + this socket's `socket_id` + the requested `channel_name`.

## Consequences

- **Pro**: Exact compatibility with `pusher-js` v8.5.0 and `laravel-echo`. Zero per-client modification.
- **Pro**: Stateless — no Redis lookup, no DB hit per subscribe. Scales linearly with connections.
- **Pro**: Non-replayable across sockets. Stealing a signature from a captured network trace and replaying on a different socket fails because the `socket_id` doesn't match.
- **Con**: Signature is stateless within the validity window of the user's session. A signature obtained for `channel = private-user.5` remains valid until the socket disconnects. We treat this as acceptable: the socket itself is the lifetime; logout invalidates the session, which kills the WS via the next protocol round-trip if the client respects 401.
- **Con**: The app secret is symmetric and shared between the HTTP auth controller and every Reverb process. `BroadcastConfig.reverb.secret` is wrapped in `SecretStr`; gitleaks gate (Article V) prevents accidental commit; rotation requires restarting all reverb processes (documented).
- For presence channels, `channel_data` is included in the signed input so a man-in-the-middle cannot substitute a different presence payload while keeping a valid signature.
