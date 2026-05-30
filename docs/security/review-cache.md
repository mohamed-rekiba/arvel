# Security Review — Cache

Area: Config cache serialization, view bytecode cache, and future runtime caches.

## Scope

Config cache written by `optimize` command, view template bytecode warm-up, and
the in-process lookup registry.

## Findings

No critical or high findings. The config cache is a local filesystem artifact written
to `bootstrap/cache/config.json`; it is not exposed over the network and is regenerated
deterministically from source.

## Controls Verified

- Cache file written with restricted permissions (umask-derived)
- No secrets serialized into the config cache (env vars resolved at runtime)
- Cache invalidated on every `optimize` run; no stale-data risk
- Bytecode cache stores only compiled template ASTs — no user data

## Next Review

Revisit when adding Redis-backed distributed cache or storing session tokens in cache.
