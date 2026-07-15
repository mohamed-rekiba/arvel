# AI: MCP Server

MCP (Model Context Protocol) is how AI agents — Claude, IDE assistants,
autonomous tools — call into applications. `arvel-ai` turns functions you mark
with `@mcp_tool` into a spec-compliant MCP server (protocol `2025-06-18`),
behind real authentication. It is **off by default**; exposing your app to
agents is a deliberate act.

## Expose a tool

Drop a decorated function in `app/mcp_tools/` — every `*.py` there is autoloaded at boot (the same
zero-wiring convention `config/` uses), so the tool is live the moment the file exists:

```python
# app/mcp_tools/order_status.py
from arvel_ai.mcp import mcp_tool

@mcp_tool(description="Look up an order's status by id")
async def order_status(order_id: int) -> str:
    order = await Order.find(order_id)
    return order.status
```

```python
# config/ai.py
ai = {
    "mcp": {
        "enabled": True,
        "public_url": "https://shop.example.com",   # canonical https URL
        # tools autoload from app/mcp_tools/; list extra modules in "tools" if needed
        "auth": {"mode": "token", "token_env": "MCP_TOKEN"},
    },
}
```

That serves `POST /mcp` (JSON-RPC: initialize, tools/list, tools/call) and
`GET /.well-known/oauth-protected-resource`. Tool input schemas derive from
your function signatures, and **arguments are validated at the boundary**
(required keys, types, no extras) before your function runs.

## Authentication

**Token mode** (dev/internal): clients send `Authorization: Bearer <token>`;
the server compares constant-time against the env var named in `token_env`.

**OIDC mode** (production): the server is an OAuth 2.1 *resource server*; any
OIDC provider (Keycloak, Auth0, ...) is the authorization server:

```python
"auth": {
    "mode": "oidc",
    "issuer": "https://idp.example.com/realms/shop",
    # jwks_uri: defaults to <issuer>/protocol/openid-connect/certs
    # audience: defaults to public_url + path
},
```

An unauthenticated request gets `401` with
`WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource"` —
that header is what makes MCP clients (Claude, IDEs) show their **login
button** and run the OAuth flow themselves: discovery, dynamic client
registration, and PKCE all happen between the client and your IdP. Tokens are
validated for signature, issuer, expiry, **and audience** — a token minted for
any other service is rejected (RFC 8707 binding).

## Security model — read before enabling

- **Tool arguments are untrusted input.** The schema gate checks shape, not
  meaning: an agent can pass any order id it likes. Authorize inside the tool
  the way you would in a route handler.
- **Design tools least-privilege.** Expose `order_status(order_id)`, not
  `run_sql(query)`. Small, specific tools are auditable; a generic escape hatch
  hands the agent your database.
- **Tool output is prompt input.** Whatever your tool returns is read by an
  LLM on the client side — a tool that echoes user-generated content can carry
  a prompt injection to the calling agent. Return data, not instructions, and
  treat stored user content in outputs with the same suspicion as rendered HTML.
- **No token passthrough.** Tools never see the caller's bearer token, and the
  gateway's upstream AI calls always use your app's own provider keys.
- **Rate-limit the route.** Put arvel's throttle middleware on `/mcp` in your
  app; the package deliberately doesn't guess your limits.
- Errors return the message only — never a traceback.

## Common mistakes & gotchas

- **`public_url` is required when enabled** — the metadata document and the
  401 challenge are built from it; a wrong value breaks client login silently.
- **OIDC needs `arvel[jwt]`** (pyjwt) for JWKS validation.
- **Tool file outside `app/mcp_tools/`** — it isn't autoloaded, the decorator
  never runs, and the tool never appears in `tools/list`. Move it into the
  folder, or list it in `mcp.tools`.
- **Testing locally:** `npx @modelcontextprotocol/inspector` speaks the same
  protocol; point it at `http://localhost:8000/mcp` with your dev token.

## See also

- [AI](ai.md) — the gateway this package is built on.
- [Authentication](../auth/authentication.md) · [Rate Limiting](../rate-limiting.md).
