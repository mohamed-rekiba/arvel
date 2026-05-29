import { defineConfig } from 'orval'

export default defineConfig({
  api: {
    input: { target: './openapi.yaml' },
    output: {
      mode: 'tags-split',
      target: './src/api/index.ts',
      schemas: './src/api/schemas',
      client: 'vue-query',
      prettier: true,
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
