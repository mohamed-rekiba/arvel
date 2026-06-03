import { defineConfig } from 'orval'

export default defineConfig({
  api: {
    input: { target: './openapi.yaml' },
    output: {
      mode: 'tags-split',
      target: './src/api/index.ts',
      schemas: './src/api/schemas',
      client: 'vue-query',
      // orval v8 defaults httpClient to 'fetch' (envelope return + url/init mutator sig).
      // Our custom mutator (src/lib/api.ts) is axios-style and returns the body directly.
      httpClient: 'axios',
      clean: true,
      override: {
        mutator: {
          path: './src/lib/api.ts',
          name: 'request',
        },
      },
    },
    hooks: {
      afterAllFilesWrite: 'node_modules/.bin/prettier --write',
    },
  },
})
