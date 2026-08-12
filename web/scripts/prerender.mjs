/**
 * Render the public routes to static HTML at build time.
 *
 * Two problems, one fix.
 *
 * **The soft 404.** `vercel.json` rewrote every path to `index.html`, so an
 * unknown URL answered HTTP 200 carrying the React 404 page. To a crawler that
 * is a real page, and a site accumulates hundreds of them.
 *
 * **Invisible copy.** The marketing pages render client-side, so their text is
 * invisible to anything that does not execute JavaScript — which is most
 * social-preview fetchers and every crawler that is not Google.
 *
 * Prerendering fixes both: each public route becomes a real file, so the
 * filesystem answers it and the catch-all rewrite can be narrowed to `/app`.
 * Anything else falls through to Vercel's `404.html` with a real 404 status.
 *
 * Deliberately not SSR. There is no server to render on — this deploys as
 * static files plus one Python function — and adding a rendering runtime to
 * make eleven pages crawlable would be a large permanent cost for a small
 * fixed problem. See docs/WEBSITE_AUDIT.md.
 *
 * ## How
 *
 * The built bundle is served by `vite preview` and driven with the Chromium
 * that already runs the e2e suite. That is real prerendering — the same code
 * path a browser takes — rather than a second rendering implementation that
 * could disagree with the first.
 */
import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { chromium } from 'playwright'

const ROOT = new URL('..', import.meta.url).pathname
const DIST = join(ROOT, 'dist')
const PORT = 4179
const BASE = `http://127.0.0.1:${PORT}`

/** Read straight out of the route table, so a new page is prerendered by
 *  existing. A hand-maintained list here is a list that goes stale.
 *
 *  Anchored on the indentation of a page entry rather than matching `path:`
 *  anywhere: breadcrumb trails carry `path` too, and a loose match prerendered
 *  every crumb as though it were a route — 26 pages from 11 routes, and a
 *  stray `dist/404/` directory from the not-found page's own crumb. */
function publicRoutes() {
  const src = readFileSync(join(ROOT, 'src', 'site', 'site.ts'), 'utf8')
  return [...src.matchAll(/^ {2}\w+: \{\n {4}path: '([^']+)'/gm)]
    .map(([, p]) => p)
    .filter((p) => !p.includes('*') && !p.startsWith('/app'))
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

async function serve() {
  const proc = spawn('npx', ['vite', 'preview', '--port', String(PORT), '--strictPort'],
                     { cwd: ROOT, stdio: 'ignore' })
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(BASE + '/')
      if (res.ok) return proc
    } catch { /* not up yet */ }
    await wait(500)
  }
  proc.kill()
  throw new Error('vite preview did not start')
}

/**
 * Strip what must not be baked into a static file.
 *
 * The hero draws its field sheet into a canvas at runtime; a serialised canvas
 * is an empty element with stale inline dimensions, and the `is-ready` class
 * would tell the fresh page it had already loaded. Removing both leaves the
 * markup React expects to mount into.
 */
const CLEAN = `
  document.querySelectorAll('canvas').forEach((c) => c.removeAttribute('style'))
  document.querySelectorAll('.hf.is-ready').forEach((e) => e.classList.remove('is-ready'))
`

async function main() {
  const routes = publicRoutes()

  /*
   * The application gets the bare shell, kept before prerendering overwrites
   * index.html.
   *
   * Without this, `/app` rewrites to an index.html carrying the *homepage's*
   * prerendered markup, and someone opening the scanner sees the marketing
   * headline for a frame before React replaces it. The app is behind a login
   * one day and is not a public route in any case: it has nothing to
   * prerender and should start empty.
   */
  writeFileSync(join(DIST, 'app.html'), readFileSync(join(DIST, 'index.html')))

  const server = await serve()
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium',
  })
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage()

  let written = 0
  try {
    for (const route of [...routes, '/__404__']) {
      await page.goto(BASE + route, { waitUntil: 'networkidle' })
      // The route table's own pages all render an h1; waiting for it is how we
      // know React ran rather than that the shell was served.
      await page.waitForSelector('h1', { timeout: 15_000 })
      await page.evaluate(CLEAN)
      const html = '<!doctype html>\n' + await page.evaluate(
        () => document.documentElement.outerHTML)

      // `/` → dist/index.html, `/scanners` → dist/scanners/index.html, so the
      // filesystem answers each URL directly and no rewrite is involved.
      const out = route === '/__404__'
        ? join(DIST, '404.html')
        : join(DIST, route === '/' ? 'index.html' : `${route.replace(/^\//, '')}/index.html`)
      mkdirSync(dirname(out), { recursive: true })
      writeFileSync(out, html)
      written++
    }
  } finally {
    await browser.close()
    server.kill()
  }
  console.log(`prerender: ${written} pages (${routes.length} routes + 404.html)`
            + ' · app.html kept as the bare shell')
}

main().catch((e) => { console.error('prerender failed:', e.message); process.exit(1) })
