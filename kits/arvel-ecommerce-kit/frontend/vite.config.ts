import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': {
        // In Docker the env var VITE_DEV_PROXY_TARGET points to the backend service name.
        // Locally fall back to localhost:8001 (default backend port).
        target: process.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8001',
        changeOrigin: true,
        // Rewrite Location headers in any 3xx response so the browser follows
        // the redirect through this proxy rather than to the backend hostname.
        autoRewrite: true,
      },
      // Local-disk media is served by the backend at /media/*.
      '/media': {
        target: process.env.VITE_DEV_PROXY_TARGET ?? 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
