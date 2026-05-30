# Frontend

Arvel is an API-first framework. It doesn't ship a built-in template engine, asset bundler, or starter UI stack — those choices belong to the frontend team.

## Recommended approaches

### API + SPA (recommended)

Treat Arvel as a typed JSON API and pair it with a separate frontend:

- **React / Next.js / Vue / Svelte** consuming Arvel's REST endpoints
- **Inertia.js-style** (FastAPI-Inertia or hand-rolled) for tighter coupling without a separate SPA build
- TanStack Query for state management on the client side

Arvel's [JSON resources](arvent-resources.md) and [responses](responses.md) make this path first-class.

### Server-rendered HTML

For server-rendered pages, render templates directly with Jinja2 inside a route handler:

```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="resources/views")


@Route.get("/")
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("home.html", {"request": request})
```

See [Views](views.md) for the conventional location and [Templates](templates.md) for template patterns.

### Live components

Arvel does not ship a Livewire equivalent. If you need server-driven reactivity, look at [Reverb](reverb.md) (WebSocket broadcasting) combined with htmx on the client side.

## Asset bundling

Arvel does not ship an asset bundler. Use [Vite](https://vitejs.dev) directly — run `npm create vite@latest` alongside your Arvel backend and point Vite's output at your static files directory.

## See also

- [Orval — Frontend API Integration](orval.md) — generate type-safe Vue Query hooks from the OpenAPI spec.
- [Views](views.md) — template directory conventions.
- [Frontend API (Orval)](orval.md) — auto-generated TypeScript client from the OpenAPI spec.
