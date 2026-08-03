/**
 * Copy MapLibre's worker (and the shared chunk it imports) into public/.
 *
 * MapLibre v6 loads its worker at runtime from a URL it computes itself, which
 * Vite's static analysis cannot see — so neither file is emitted, and the app
 * silently renders an empty map: the worker 404s, the SPA rewrite hands it
 * index.html, it fails to parse, and every GeoJSON source stays unloaded
 * forever with no console error and no map error event.
 *
 * `?url` does not solve it either: it copies one file without its dependency
 * graph, and the worker's `import "./maplibre-gl-shared.mjs"` then 404s the
 * same way.
 *
 * public/ is copied verbatim by Vite — original filenames, no hashing — which
 * is exactly what a relative import between two sibling files needs. Wired to
 * both predev and prebuild so dev and production behave identically; the
 * divergence is what hid this bug in the first place.
 */
import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const from = join(here, '..', 'node_modules', 'maplibre-gl', 'dist')
const to = join(here, '..', 'public', 'maplibre')

mkdirSync(to, { recursive: true })
for (const f of ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs']) {
  copyFileSync(join(from, f), join(to, f))
}
console.log('maplibre worker copied to public/maplibre/')
