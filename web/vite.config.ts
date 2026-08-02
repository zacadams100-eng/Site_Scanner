import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend runs on :8000 (mock_ee_backend or app). Proxying /api keeps the
// frontend origin-agnostic, so the same build works against a deployed API
// without a rebuild.
export default defineConfig({
  plugins: [react()],
  // MapLibre ships its own web worker. Pre-bundling rewrites the worker import
  // in a way the browser then fails to fetch, so it is excluded from dep
  // optimisation and loaded as-is.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})
