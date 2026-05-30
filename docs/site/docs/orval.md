# Frontend API Integration with Orval

Arvel's fullstack starter uses [Orval](https://orval.dev) to generate a type-safe API client directly from the backend's OpenAPI spec. Every time the backend changes, one command regenerates strongly-typed [TanStack Vue Query](https://tanstack.com/query/latest) hooks and [Zod](https://zod.dev) validation schemas — no hand-written types, no drift.

## How it works

```
backend/docs/api/openapi.yaml
        │
        ▼  npm run orval
src/generated/api/
├── auth.ts          ← useAuthLogin(), useAuthMe(), …
├── items.ts         ← useGetItems(), usePostItems(), …
└── schemas/
    └── …            ← ItemBody, PaginatedItems, …
```

Orval reads `../backend/docs/api/openapi.yaml` and emits two outputs:

| Output | Client | Location |
|---|---|---|
| Vue Query hooks | `vue-query` | `src/generated/api/` |
| Zod schemas | `zod` | `src/generated/api/*.zod.ts` |

The generated tree is **committed to source control** so teammates and CI never need the backend running to build or type-check the frontend.

## Prerequisites

- Node ≥ 20 (the `engines` field in `package.json` enforces this)
- `orval` installed as a dev dependency — already present in the fullstack-vue starter

```bash
npm install --save-dev orval
```

## Configuration

The config lives at `frontend/orval.config.ts`:

```ts
import { defineConfig } from 'orval';

export default defineConfig({
  arvel: {
    input: {
      target: '../backend/docs/api/openapi.yaml',
    },
    output: {
      mode: 'tags-split',           // one file per OpenAPI tag
      target: './src/generated/api/index.ts',
      schemas: './src/generated/api/schemas',
      client: 'vue-query',
      mock: false,
      prettier: true,
      override: {
        mutator: {
          path: './src/lib/api.ts', // the custom fetcher (see below)
          name: 'arvelFetcher',
        },
        useTypeOverInterfaces: true,
      },
    },
    hooks: {
      afterAllFilesWrite: 'prettier --write',
    },
  },
  zod: {
    input: {
      target: '../backend/docs/api/openapi.yaml',
    },
    output: {
      mode: 'tags-split',
      client: 'zod',
      target: './src/generated/api/zod.ts',
      fileExtension: '.zod.ts',
      prettier: true,
    },
  },
});
```

Key settings:

- **`mode: 'tags-split'`** — groups hooks by the OpenAPI `tags` field. If your backend tags `POST /items` with `items`, the generated hook lands in `src/generated/api/items.ts`.
- **`mutator`** — points Orval at a custom fetch function instead of `axios`. This is where auth headers, CSRF, and locale propagation happen.

## The custom fetcher

All generated hooks call `arvelFetcher` from `src/lib/api.ts`. It handles:

| Concern | Mechanism |
|---|---|
| Bearer auth | Reads `accessToken` from the `useAuthStore` Pinia store |
| CSRF | Double-submit cookie (`_csrf` → `X-CSRF-TOKEN`) on unsafe verbs |
| Locale | Propagates `Accept-Language` from `useLocaleStore` |
| Errors | Throws `ApiError` with an unwrapped RFC 7807 body |
| 204 responses | Returns `undefined` — no attempt to parse an empty body |

You don't need to touch this file for normal API usage. Override it only when you need project-specific transport behaviour.

### `ApiError`

Every non-2xx response rejects with an `ApiError`:

```ts
class ApiError extends Error {
  readonly status: number;   // HTTP status code
  readonly body: ApiErrorBody; // RFC 7807 problem-details

  // Returns field → messages[] from a 422 validation response.
  fieldErrors(): Record<string, string[]>;
}
```

## Generating the client

With the stack running:

=== "npm script"

    ```bash
    npm run orval
    ```

=== "Make target (inside the package root)"

    ```bash
    make orval
    ```

=== "Docker Compose (from inside the running container)"

    ```bash
    docker compose exec frontend npm run orval
    ```

The backend must have written `backend/docs/api/openapi.yaml` before you run this. In local dev the file is committed; in CI it's exported before the frontend build step runs.

### Exporting the spec from the backend

The backend can export its current OpenAPI document with:

```bash
arvel openapi:export --output docs/api/openapi.yaml
```

Or, if you have the stack running, fetch it directly from the running server:

```bash
curl http://localhost:8000/openapi.json -o backend/docs/api/openapi.yaml
```

## Using generated hooks

Orval generates one hook per operationId. A `GET /items` endpoint tagged `items` with `operationId: getItems` produces `useGetItems`.

### Queries (reads)

```vue
<script setup lang="ts">
import { useGetItems } from '@/generated/api/items';

const { data, isPending, isError, error } = useGetItems({
  page: 1,
  per_page: 20,
  sort: '-created_at',
});
</script>

<template>
  <div v-if="isPending">Loading…</div>
  <div v-else-if="isError">{{ error.message }}</div>
  <ul v-else>
    <li v-for="item in data?.data" :key="item.id">{{ item.title }}</li>
  </ul>
</template>
```

### Mutations (writes)

```vue
<script setup lang="ts">
import { usePostItems } from '@/generated/api/items';

const mutation = usePostItems();

function submit(payload: { title: string; category: string }) {
  mutation.mutate(payload, {
    onSuccess: () => { /* redirect or toast */ },
    onError: (error) => { /* show error */ },
  });
}
</script>
```

### Invalidating related queries after a mutation

Use the `useQueryClient` hook to invalidate stale query caches:

```ts
import { useQueryClient } from '@tanstack/vue-query';
import { useDeleteItemsId } from '@/generated/api/items';

const queryClient = useQueryClient();

const deletion = useDeleteItemsId({
  mutation: {
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['items'] });
    },
  },
});
```

## Error handling

Use the `useApiError` composable to turn any thrown error into a localised string:

```ts
import { useApiError } from '@/composables/useApiError';

const { messageFor, fieldErrors } = useApiError();
```

| Function | Returns | Use for |
|---|---|---|
| `messageFor(error)` | `string` | Toast messages, inline banners |
| `fieldErrors(error)` | `Record<string, string[]>` | Attaching validation messages to form fields (422 only) |

The backend already returns translated `detail` and `title` strings via the `Accept-Language` header, so `messageFor` usually just surfaces those. It falls back to generic i18n keys for network errors and 5xx responses with no body.

### Example with a form

```vue
<script setup lang="ts">
import { usePostItems } from '@/generated/api/items';
import { useApiError } from '@/composables/useApiError';

const { messageFor, fieldErrors } = useApiError();

const mutation = usePostItems();
const errors = ref<Record<string, string[]>>({});

function submit(payload: { title: string; category: string }) {
  errors.value = {};
  mutation.mutate(payload, {
    onError: (error) => {
      errors.value = fieldErrors(error);
      if (!Object.keys(errors.value).length) {
        toast.error(messageFor(error));
      }
    },
  });
}
</script>
```

## Keeping generated code fresh

The generated files are committed. CI runs a drift check to catch any mismatch between the spec and the committed output:

```bash
npx orval --check
```

This exits non-zero if the generated output would differ from what's on disk. Run it as part of your CI pipeline alongside `vue-tsc --noEmit` and `eslint`.

Add to your CI workflow:

```yaml
- name: Check generated API client is up to date
  run: npm run orval -- --check
  working-directory: frontend
```

## Adding Orval to a plain Arvel project

If you're wiring Orval into a project that doesn't use the fullstack-vue starter:

1. **Install Orval**

    ```bash
    npm install --save-dev orval
    ```

2. **Add a script** to `package.json`

    ```json
    "scripts": {
      "orval": "orval --config orval.config.ts"
    }
    ```

3. **Create `orval.config.ts`** — copy the config from the starter and update the `input.target` path.

4. **Create the custom fetcher** at `src/lib/api.ts` — copy `arvelFetcher` from the starter. Update the Pinia store imports if your store names differ.

5. **Wire TanStack Vue Query** in `main.ts` (it's a peer dependency of the generated hooks):

    ```ts
    import { VueQueryPlugin } from '@tanstack/vue-query';
    app.use(VueQueryPlugin);
    ```

6. **Run `npm run orval`** to generate the initial client.

## Troubleshooting

**`Error: Input file not found`**

The path in `orval.config.ts` → `input.target` doesn't point to a valid YAML file. Make sure the backend has exported its spec:

```bash
arvel openapi:export --output docs/api/openapi.yaml
```

**Generated files are out of date in CI**

Run `npm run orval -- --check` in CI before the build step. Fail fast and require developers to regenerate locally before merging.

**Hook name doesn't match what I expect**

Orval derives hook names from `operationId`. Check the `operationId` on your route in `openapi.yaml`. If the backend doesn't set one explicitly, Arvel auto-generates it as `{tag}_{verb}_{path_slugified}`.

**Type errors after regeneration**

Run `vue-tsc --noEmit` after regenerating. If the backend removed or renamed a field, the compiler will point at every consumer that needs updating.

## See also

- [Routing](routing.md) — how the backend defines endpoints that show up in the OpenAPI spec
- [Resources & responses](responses.md) — how response shapes are documented
- [Frontend](frontend.md) — frontend conventions and stack overview
- [Frontend](frontend.md) — frontend integration overview
