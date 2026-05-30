# Views

Arvel doesn't ship a built-in template engine. For server-rendered HTML, the convention is to use **Jinja2** directly through FastAPI's `Jinja2Templates` integration.

## Conventional location

```
resources/
└── views/
    ├── layouts/
    │   └── base.html
    ├── home.html
    └── users/
        └── show.html
```

## Wiring up Jinja2

```python
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import HTMLResponse

from arvel.facades import Route

templates = Jinja2Templates(directory="resources/views")


@Route.get("/users/{user_id}", response_class=HTMLResponse)
async def show_user(request: Request, user_id: int) -> HTMLResponse:
    user = await User.find_or_fail(user_id)
    return templates.TemplateResponse(
        "users/show.html",
        {"request": request, "user": user.to_dict()},
    )
```

## Template bytecode caching

Jinja2 can pre-compile templates to bytecode and cache the result to disk. Subsequent renders skip the parse step entirely, which speeds up the first request after a cold start.

```bash
arvel view:cache    # compile all templates to bootstrap/views/
arvel view:clear    # delete bootstrap/views/ and reset the in-process Jinja environment
```

The cache lives in `bootstrap/views/`. Add it to `.gitignore` (the default starter already does).

Run `view:cache` at the end of your deploy script so cold-start latency doesn't affect real traffic:

```bash
# Dockerfile / deploy hook
uv run arvel view:cache
```

Run `view:clear` to force a rebuild — useful when you change templates during local development and want to be sure the cache is regenerated:

```bash
uv run arvel view:clear
```

Or use `optimize` / `optimize:clear` to compile both config and views in a single step. See [Console — Production caches](console.md#production-caches).

## Why not a built-in template engine?

Arvel is API-first. The framework optimizes for typed JSON endpoints and lets the frontend layer choose its own tools. When you need server-rendered HTML, Jinja2 is the Python ecosystem standard — Arvel doesn't reinvent it.

## See also

- [Templates](templates.md) — template-language patterns (Jinja2 conventions).
- [Frontend](frontend.md) — how frontend integration works overall.
- [Responses](responses.md) — returning HTML responses.
