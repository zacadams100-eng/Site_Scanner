import { describe, expect, it } from 'vitest'
// Vite's raw import rather than node:fs — the app's tsconfig does not carry
// node types, and a test that only compiles under a different config is a test
// that breaks the production build.
import SOURCE from './api.ts?raw'
import STORE_SOURCE from './store.ts?raw'

/**
 * Every scanner-scoped route must take a scanner, by signature.
 *
 * The e2e suite asserts that observed assessment requests carry the active
 * scanner — but it can only observe the routes the journey happens to issue,
 * which is `/api/series` and `/api/cells`. `/api/brief`, `/api/ask` and
 * `/api/compare` are equally scoped on the backend and are not exercised by
 * drawing a rectangle, so a regression in any of those would pass a green e2e
 * run.
 *
 * This closes that gap statically. If a scoped function stops requiring a
 * scanner it stops compiling at every call site, which is a much harder thing
 * to do by accident than forgetting to pass one.
 *
 * The original defect was exactly this: the frontend sent the scanner on the
 * catalogue and on nothing else, so a report opened inside Habitat came back
 * assessed by Land's rules. It was later found a second time on `/api/ask`.
 */

/** Every function that posts to a route the backend resolves a scanner for.
 *  Adding a scoped route means adding it here. */
const SCOPED = ['fetchSeries', 'fetchBrief', 'fetchCells', 'ask', 'compareSites']

function signatureOf(name: string): string {
  const start = SOURCE.indexOf(`export function ${name}(`)
  expect(start, `${name} is not exported from api.ts`).toBeGreaterThan(-1)
  return SOURCE.slice(start, SOURCE.indexOf('{', SOURCE.indexOf('):', start)))
}

describe('scanner identity travels with the work', () => {
  it.each(SCOPED)('%s takes a required scanner', (name) => {
    const signature = signatureOf(name)
    expect(signature).toMatch(/\bscanner:\s*string\b/)
    // Not optional and not defaulted. A `scanner?: string` or a
    // `scanner = 'land'` would compile at every existing call site and
    // reintroduce the original bug silently.
    expect(signature).not.toMatch(/\bscanner\?\s*:/)
    expect(signature).not.toMatch(/\bscanner:\s*string\s*=/)
  })

  it.each(SCOPED)('%s puts the scanner in the request body', (name) => {
    const start = SOURCE.indexOf(`export function ${name}(`)
    const body = SOURCE.slice(start, start + 900)
    expect(body).toMatch(/\bscanner\b\s*[,}]/)
  })

  it('no scoped route hardcodes a scanner id', () => {
    // `fetchSeries(aoi, selected, 'land', signal)` is what the bug looked like
    // in the store, and it type-checks.
    for (const name of SCOPED) {
      const start = SOURCE.indexOf(`export function ${name}(`)
      const body = SOURCE.slice(start, start + 900)
      expect(body).not.toMatch(/scanner:\s*['"](land|habitat|coastal)['"]/)
    }
  })

  it('the store passes the active scanner rather than a literal', () => {
    for (const call of STORE_SOURCE.matchAll(/fetch(Series|Cells|Brief)\(([^)]*)\)/g)) {
      expect(call[2], `${call[0]} hardcodes a scanner`)
        .not.toMatch(/['"](land|habitat|coastal)['"]/)
    }
  })
})
