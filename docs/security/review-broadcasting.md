# Security Review — Broadcasting

Area: Reverb WebSocket server and channel authorization.

## Scope

Channel presence authorization, private channel access control, broadcast payload
validation, and connection lifecycle security.

## Findings

No critical or high findings. Private and presence channels require a signed authorization
token issued by the backend; public channels carry no sensitive data.

## Controls Verified

- Channel auth endpoint validates JWT before issuing channel tokens
- Presence channel payloads expose only the user's own `user_id` and display name
- No PII in public broadcast payloads
- Connection tokens expire with the originating JWT

## Next Review

Revisit when adding client-to-client whisper events or expanding channel namespaces.
