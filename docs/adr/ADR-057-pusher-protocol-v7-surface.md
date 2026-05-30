# ADR-057: Pusher Protocol v7 — What We Implement, What We Don't

**Status**: Accepted
**Date**: 2026-05-18

## Context

The Pusher Channels v7 protocol has a wide surface. Implementing it all is overkill for an MVP; cherry-picking is dangerous because `pusher-js` / `laravel-echo` expect specific frames. Need to fix a contract that satisfies the common clients without overspending.

## Decision

We implement the minimum subset required for `pusher-js` v8.5.0 and `laravel-echo` v1.x to function for public, private, and presence channels:

**Server → client frames**:
- `pusher:connection_established` (on WS open, with `{socket_id, activity_timeout}`)
- `pusher:error` (codes 4200 invalid msg, 4009 auth failed, 4301 rate limited; full Pusher 4xxx code list documented but only these three emitted)
- `pusher:pong`
- `pusher_internal:subscription_succeeded`
- `pusher_internal:member_added` / `pusher_internal:member_removed` (presence only)

**Client → server frames**:
- `pusher:ping`
- `pusher:subscribe` (with optional `auth` + `channel_data`)
- `pusher:unsubscribe`

We explicitly do NOT implement:
- `client-*` events (client-initiated direct messages).
- `pusher:signin` (user authentication binding — a v7.2 addition).
- `pusher:cache_miss`, `pusher:cache_*` (cache channels).
- The `?protocol=N` query parameter for protocol negotiation — we accept any value and reply with the v7 frames regardless.

A `tests/reverb/test_pusherjs_contract.py` runs a Node subprocess with `pusher-js@8.5.0` against an in-process `ReverbServer` to assert the contract works against the real client. If `pusher-js` changes incompatibly upstream, this test catches it.

## Consequences

- **Pro**: ~70 % of the protocol delivered with ~30 % of the spec text. Common-case clients work without modification.
- **Pro**: Contract-test pinning means breaking changes upstream surface as a failed CI check, not as a silent runtime bug.
- **Con**: Users who need `client-*` events (e.g., for typing indicators broadcast peer-to-peer without server round-trip) cannot. Documented; defer to a future WI if real demand surfaces.
- **Con**: The protocol-version query parameter is ignored — a v8 client expecting v8 semantics would get v7. Mitigated by the fact that `pusher-js` v8.5.0 sends `protocol=7` itself; upgrade-path pain is hypothetical.
- Frame parsing errors yield `pusher:error code=4200`; auth failures `code=4009`; rate-limit `code=4301`. No other error codes are emitted.
