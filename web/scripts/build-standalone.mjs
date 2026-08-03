/**
 * Fold the built app into one HTML file that runs with no server.
 *
 * The deployable build fetches its JS, CSS, fonts and MapLibre's worker as
 * separate files. A single-file build has nowhere to fetch from, so each of
 * those becomes inline text or a data URI, and the worker — normally two files
 * with a relative import between them — is pre-bundled into one self-contained
 * module and handed over as a blob at runtime.
 *
 * Run after `VITE_STANDALONE=1 vite build`:
 *   node scripts/build-standalone.mjs
 */
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { rolldown } from 'rolldown'

const here = dirname(fileURLToPath(import.meta.url))
const web = join(here, '..')
const dist = join(web, 'dist-standalone')
const out = join(web, 'dist-standalone', 'site-scanner-standalone.html')

if (!existsSync(dist)) {
  console.error('No dist-standalone/. Run: VITE_STANDALONE=1 npx vite build')
  process.exit(1)
}

const assets = join(dist, 'assets')
const names = readdirSync(assets)
const jsFiles = names.filter((n) => n.endsWith('.js'))
const cssFiles = names.filter((n) => n.endsWith('.css'))

// One chunk is the whole point — see the codeSplitting: false in vite.config.
// If this ever trips, the page would silently lose whatever was in chunk two.
if (jsFiles.length !== 1) {
  console.error(`Expected exactly 1 JS chunk, found ${jsFiles.length}: ${jsFiles.join(', ')}`)
  process.exit(1)
}

const b64 = (buf) => Buffer.from(buf).toString('base64')

// ---- CSS, with its fonts folded in -----------------------------------------
let css = cssFiles.map((f) => readFileSync(join(assets, f), 'utf8')).join('\n')
css = css.replace(/url\(\s*["']?\/fonts\/([^"')]+)["']?\s*\)/g, (whole, file) => {
  const p = join(web, 'public', 'fonts', file)
  if (!existsSync(p)) {
    console.warn(`  ! font not found, leaving as-is: ${file}`)
    return whole
  }
  return `url("data:font/woff2;base64,${b64(readFileSync(p))}")`
})

// ---- MapLibre's worker, bundled into one module ----------------------------
// The shipped worker imports a sibling shared chunk. A blob URL has no base to
// resolve that against, so the import has to be inlined before it can be one.
const bundle = await rolldown({
  input: join(web, 'node_modules', 'maplibre-gl', 'dist', 'maplibre-gl-worker.mjs'),
  logLevel: 'silent',
})
const generated = await bundle.generate({ format: 'esm', codeSplitting: false })
const workerSource = generated.output.filter((o) => o.type === 'chunk').map((o) => o.code).join('\n')
if (/^\s*import[\s{]/m.test(workerSource)) {
  console.error('Worker bundle still has imports; a blob URL cannot resolve them.')
  process.exit(1)
}

const js = readFileSync(join(assets, jsFiles[0]), 'utf8')
const favicon = readFileSync(join(web, 'public', 'favicon.svg'), 'utf8')

// `</script>` anywhere inside an inline script ends it early, wherever it
// appears — including inside a string literal. The worker source is third-party
// and long; escaping is cheaper than trusting it not to contain one.
const safe = (s) => s.replace(/<\/script/gi, '<\\/script')

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,${b64(favicon)}" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#1d2836" />
    <meta name="description" content="Site Scanner — GIS for land management. Standalone demo: every number is generated." />
    <title>Site Scanner — standalone demo</title>
    <style>${css}</style>
  </head>
  <body>
    <div id="root"></div>
    <script>window.__MAPLIBRE_WORKER__ = ${JSON.stringify(workerSource).replace(/<\/script/gi, '<\\/script')};</script>
    <script type="module">${safe(js)}</script>
  </body>
</html>
`

writeFileSync(out, html)
const mb = (html.length / 1024 / 1024).toFixed(2)
console.log(`standalone -> ${out}  (${mb} MB)`)
console.log(`  js ${(js.length / 1024).toFixed(0)} kB · css ${(css.length / 1024).toFixed(0)} kB · worker ${(workerSource.length / 1024).toFixed(0)} kB`)
