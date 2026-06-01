# ADR-106: `Broadcast.channel()` Registry — Exact Pattern Matching, No Wildcards

**Status**: Accepted
**Date**: 2026-05-18

## Context

`Broadcast.channel("private-user.{id}")` registers an auth callback. Three candidates for the matching semantics:

- **A**: Full regex (`@Broadcast.channel(r"^private-user\.(?P<id>\d+)$")`) — power user friendly, security-tricky.
- **B**: Exact pattern with `{placeholder}` substitutions matching `[^./]+` — Laravel-style, predictable.
- **C**: Prefix match + parameter parsing (`"private-user.*"` → all `private-user.*` channels) — simple but ambiguous.

## Decision

**Option B** — Patterns use `{name}` placeholders. Each placeholder compiles to a `(?P<name>[^./]+)` regex group; the rest of the pattern is `re.escape`'d. Match is anchored with `fullmatch`.

Examples:
- `"private-user.{id}"` matches `"private-user.5"` (id=`"5"`) and `"private-user.alice"` (id=`"alice"`).
- `"private-user.{id}"` does NOT match `"private-user.5.admin"` (the `.admin` segment falls outside the placeholder class).
- `"presence-team.{team}.room.{room}"` matches `"presence-team.42.room.3"` (team=`"42"`, room=`"3"`).

Multiple patterns may be registered; lookup is first-match-wins in registration order.

## Consequences

- **Pro**: Whole classes of channel-name injection bugs are eliminated by construction. `"private-../admin"` cannot match `"private-user.{id}"` — `..` falls outside `[^./]+`.
- **Pro**: Matches Laravel's `Broadcast::channel("private-user.{userId}", ...)` mental model exactly.
- **Pro**: No user-supplied regex; users can't accidentally write a catastrophic-backtracking pattern.
- **Con**: No globs or wildcards. Users wanting "all private-* channels go through one callback" must register one pattern per shape. We consider this a feature, not a limitation — explicit > magic.
- Duplicate-pattern registration raises `BroadcastException` at register time (loud, not silent).
