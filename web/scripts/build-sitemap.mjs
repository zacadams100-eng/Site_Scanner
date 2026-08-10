/**
 * Generate sitemap.xml from the one route table.
 *
 * Run at build time so the sitemap cannot drift from the routes — a
 * hand-maintained sitemap is a list of URLs that used to exist.
 *
 * **Writes nothing without `VITE_SITE_ORIGIN`.** A sitemap of relative paths is
 * invalid, and one pointing at a placeholder domain tells search engines about
 * a site that is not there. No origin, no sitemap, and the build says so.
 */
import { writeFileSync, existsSync, unlinkSync } from 'node:fs'
import { readFileSync } from 'node:fs'

const origin = (process.env.VITE_SITE_ORIGIN ?? '').replace(/\/$/, '')
const out = new URL('../public/sitemap.xml', import.meta.url)

if (!origin) {
  if (existsSync(out)) unlinkSync(out)
  console.log('sitemap: skipped — VITE_SITE_ORIGIN is not configured')
  process.exit(0)
}

// Read the paths straight out of the route table rather than restating them.
const src = readFileSync(new URL('../src/site/site.ts', import.meta.url), 'utf8')
const entries = [...src.matchAll(/path:\s*'([^']+)'[\s\S]*?indexable:\s*(true|false)/g)]
  .filter(([, , indexable]) => indexable === 'true')
  .map(([, path]) => path)

const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries.map((p) => `  <url><loc>${origin}${p}</loc></url>`).join('\n')}
</urlset>
`
writeFileSync(out, xml)
console.log(`sitemap: ${entries.length} public routes`)
