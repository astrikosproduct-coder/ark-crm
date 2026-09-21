import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // Pinned, and strict on purpose. Vite silently falls back to 5174 when 5173
    // is busy, and the Entra app registration lists ONE redirect URI — a
    // silent port change makes Microsoft reject every sign-in with an error
    // that does not explain itself. Fail on start instead.
    port: 5173,
    strictPort: true,
    // Every /api request goes to FastAPI. One entry since MSW was removed
    // (21 Sep 2026): before that each migrated path needed its own entry here
    // AND a passthrough in the mock handlers, and missing either returned
    // Vite's HTML page instead of JSON. In production the reverse proxy in
    // front of the app does this job — see frontend/Caddyfile.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
