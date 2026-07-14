# AI

One stable API over many AI providers. `arvel-ai` gives your app chat,
streaming, structured output, tool definitions, and embeddings through the
house driver pattern — swap providers in config, never in code — plus a
[secured MCP server](ai-mcp.md) that makes your app callable by AI agents.

```bash
uv add 'arvel-ai[litellm]'
```

Installing registers the provider automatically; `app.make("ai")` and the `AI`
facade work with zero wiring.

## Chat

```python
from arvel_ai import AI

reply = await AI.chat("Summarize this review: ...", model="fast")
print(reply.text)
```

A plain string becomes a user message. Full control uses the same shapes
everywhere — no provider SDK types anywhere:

```python
from arvel_ai import ChatRequest, Message

response = await AI.chat(
    [Message(role="user", content="Three names for a sock brand")],
    system="You are terse.",
    max_tokens=200,
    options={"temperature": 0.8},   # provider passthrough, not part of the stable surface
)
```

`response.stop_reason` is one of `end_turn / max_tokens / tool_use / refusal /
other`; `response.usage` carries token counts (and cache reads where the
provider reports them).

## Streaming

```python
async for delta in AI.stream("Write a product description"):
    match delta:
        case TextDelta(text=chunk):
            print(chunk, end="")
        case StreamEnd(response=response):
            record(response.usage)
```

## Structured output

Define the shape as a msgspec Struct; the gateway asks the provider for schema-
constrained output and decodes it for you:

```python
import msgspec

class ProductCopy(msgspec.Struct):
    title: str
    bullets: list[str]

copy = await AI.structured(ProductCopy, "Write copy for red wool socks")
```

## Tools

Tool definitions and calls ride on the request/response — your agent loop, your
control:

```python
from arvel_ai import ToolDef, ToolResult

response = await AI.chat(
    "What's the weather in Paris?",
    tools=[ToolDef(name="get_weather", description="...", input_schema={...})],
)
for call in response.tool_calls:
    result = run_tool(call)         # your dispatch
    followup = await AI.chat([...prior, Message(role="user", content=[
        ToolResult(tool_call_id=call.id, content=result)])], tools=[...])
```

## Drivers & model aliases

```python
# config/ai.py (host app)
ai = {
    "default": "litellm",
    "models": {"fast": "claude-haiku-4-5", "smart": "claude-opus-4-8"},
}
```

- **litellm** (default) — the LiteLLM SDK: 100+ providers, keys via each
  provider's own env var.
- **openai_compatible** — any OpenAI-format endpoint: a deployed LiteLLM proxy,
  vLLM, Ollama. Needs `base_url`; key via the env var named in `api_key_env`.
- **fake** — the test double (below).

`models` is the churn shield: apps say `model="fast"`; a provider retiring a
model is one config edit and a patch release, zero code changes. **Versioning
policy:** arvel-ai follows semver — the request/response shapes and error
taxonomy only break on a major; drivers and default models can update in
minors/patches.

## Testing — `AI.fake()`

The fake is a first-class driver, so tests swap it in exactly the way
production swaps providers:

```python
def test_review_summary(client):
    fake = AI.fake()
    fake.replies = ["Great quality, runs small."]
    response = client.post("/products/1/summarize")
    fake.assert_chatted("runs small")   # and: fake.requests[-1].model, .messages
```

## Errors

One taxonomy, whatever the provider: `AiAuthError`, `AiInvalidRequest`,
`AiRateLimited` (with `.retry_after`), `AiProviderError`, `AiTimeout`,
`AiContentFiltered`, `AiCapabilityError` — each with a `.retryable` flag.
Catch `AiError` for all of them.

## Observability

Every call opens a gated telemetry span (`ai.chat` / `ai.stream` / `ai.embed`,
token usage as attributes — a no-op unless the `telemetry` extra is configured)
and dispatches events your app can hook:

```python
from arvel_ai.events import AiResponseReceived
app.make("events").listen(AiResponseReceived, audit_ai_usage)
```

## Common mistakes & gotchas

- **Extras:** the default driver needs `uv add 'arvel-ai[litellm]'`; the
  openai_compatible driver needs `arvel-ai[httpx]`. A missing engine tells you
  exactly that.
- **Keys live in env vars** — the config holds env var *names*, never values.
- **`temperature` is passthrough, not stable API** — some providers reject
  sampling parameters entirely; anything in `options` is between you and the
  configured provider.
- **Embeddings are per-driver** — a provider without an embeddings endpoint
  raises `AiCapabilityError`; route embeddings through a driver that has them.

## See also

- [MCP Server](ai-mcp.md) — expose your app's functions to AI agents, with auth.
- [Telemetry](../telemetry.md) · [Events](../events.md) · [Queues](../queues.md)
  for background AI jobs.
