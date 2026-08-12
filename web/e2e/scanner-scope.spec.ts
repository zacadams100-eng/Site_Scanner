import { expect, test, type Request } from '@playwright/test'
import { drawSite, launchScanner, openLibrary } from './helpers'

/**
 * Regression cover for the second defect found by hand, and the more serious
 * of the two.
 *
 * `ScannedRequest.scanner` defaults to land on the backend. The frontend sent
 * the scanner on `/api/catalog` but on none of the assessment routes, so a
 * report opened inside Habitat came back assessed by Land's rules against
 * Land's 271 factors. Nothing failed: the shell said HABITAT, the numbers were
 * Land's, and the two were indistinguishable without knowing what Habitat's
 * factor count should have been.
 *
 * That is why this spec checks the wire as well as the screen. A rendered
 * count can be made to look right; the request either carried the scanner or
 * it did not.
 */

/** Every route that runs an assessment and is therefore scanner-scoped. */
const SCOPED = ['/api/series', '/api/cells', '/api/brief', '/api/ask', '/api/compare']

function scannerOf(req: Request): string | undefined {
  try {
    return (req.postDataJSON() as { scanner?: string })?.scanner
  } catch {
    return undefined
  }
}

test('every assessment request carries the active scanner', async ({ page }) => {
  const seen: { url: string; scanner?: string }[] = []
  page.on('request', (req) => {
    const path = new URL(req.url()).pathname
    if (SCOPED.includes(path)) seen.push({ url: path, scanner: scannerOf(req) })
  })

  await openLibrary(page)
  await launchScanner(page, 'Ecology')
  await drawSite(page)

  // The journey must actually have issued scoped requests, or this test would
  // pass by having tested nothing.
  expect(seen.length, 'no assessment requests were observed').toBeGreaterThan(0)

  const wrong = seen.filter((r) => r.scanner !== 'ecology')
  expect(wrong, `requests that did not carry scanner=ecology: ${JSON.stringify(wrong)}`)
    .toEqual([])
})

test('the Ecology report is scoped to Ecology factors', async ({ page, request }) => {
  // Independent source of truth: ask the API directly what each scanner has.
  // Deriving the expectation from the same request path under test would make
  // the assertion circular.
  const counts: Record<string, number> = {}
  for (const id of ['land', 'ecology']) {
    const res = await request.get(`/api/catalog?scanner=${id}`)
    expect(res.ok(), `catalogue for ${id} did not load`).toBe(true)
    counts[id] = ((await res.json()).factors as unknown[]).length
  }

  // If the two scanners ever have the same number of factors this test stops
  // being able to tell them apart, and should fail loudly rather than quietly
  // pass forever.
  expect(counts.ecology, 'Land and Ecology have the same factor count — this '
    + 'test can no longer distinguish them').not.toBe(counts.land)

  await openLibrary(page)
  await launchScanner(page, 'Ecology')
  await drawSite(page)

  // The denominator is the scanner's own factor list. Before the fix this read
  // Land's count in Ecology's shell.
  const coverage = await page.locator('.ovw-coverage').innerText()
  const denominator = Number(coverage.match(/of (\d+) factors/)?.[1])
  expect(denominator, `coverage read "${coverage}"`).toBe(counts.ecology)
})

test('switching scanners does not carry the previous report across', async ({ page }) => {
  await openLibrary(page)
  await launchScanner(page, 'Land')
  await drawSite(page)
  await expect(page.locator('.ovw-coverage')).toBeVisible()

  await page.getByRole('button', { name: 'Back to all scanners' }).click()
  await launchScanner(page, 'Ecology')

  // A site assessed by one scanner is not a site assessed by the other, so the
  // drawn shape and its report are cleared rather than reinterpreted.
  await expect(page.locator('.ovw-coverage')).toHaveCount(0)
  await expect(page.locator('.brand-scanner')).toHaveText('Ecology')
})
