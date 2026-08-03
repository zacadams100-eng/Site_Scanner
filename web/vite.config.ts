import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend runs on :8000 (mock_ee_backend or app). Proxying /api keeps the
// frontend origin-agnostic, so the same build works against a deployed API
// without a rebuild.
// The standalone build becomes one HTML file (see scripts/build-standalone.mjs),
// so it must not be split across chunks — a second chunk would be a fetch to a
// file that no longer exists. It also writes somewhere else, so a standalone
// build never clobbers the deployable one.
const standalone = process.env.VITE_STANDALONE === '1'

export default defineConfig({
  plugins: [react()],
  build: standalone
    ? { outDir: 'dist-standalone', rolldownOptions: { output: { codeSplitting: false } } }
    : {},
  // MapLibre ships its own web worker, and it needs handling at both ends.
  //
  // Dev: pre-bundling rewrites the worker import in a way the browser then
  // fails to fetch, so maplibre is excluded from dep optimisation.
  //
  // Build: MapLibre asks for `new Worker(url, { type: 'module' })`, but Vite
  // emits IIFE workers by default. The mismatch fails *silently* — no console
  // error, no map error event — and the only symptom is that every GeoJSON
  // source stays unloaded forever, so the map renders nothing while the rest
  // of the app looks perfectly healthy. Emitting ES workers fixes it.
  worker: { format: 'es' },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})
