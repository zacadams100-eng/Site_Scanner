import { expect, test } from '@playwright/test'
import { drawSite, launchScanner, openLibrary, openTab, watchConsole } from './helpers'

/**
 * The main journey, end to end: arrive, choose a scanner, draw a site, read the
 * report.
 *
 * One test rather than six, deliberately. Each step depends on the one before,
 * so split into separate tests they would each have to repeat the whole setup —
 * paying for the map and the series four times to assert four things.
 */

test('a visitor can reach the product from the public site', async ({ page }) => {
  const guard = watchConsole(page)

  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  await page.goto('/scanners')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  // The scanners page lists the two built scanners by name.
  await expect(page.getByRole('main')).toContainText('Land')
  await expect(page.getByRole('main')).toContainText('Habitat')

  await page.goto('/scanners/land')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  expect(guard.errors, guard.errors.join('\n')).toEqual([])
})

test('a site can be drawn and its report read', async ({ page }) => {
  const guard = watchConsole(page)

  await openLibrary(page)
  // The library shows exactly the scanners the API reports as implemented.
  // Asserted against the API rather than a literal, because the literal was 2
  // and Coastal shipping made it 3 — a test that breaks when the product grows
  // is a test that gets edited rather than read.
  const built = await page.evaluate(async () => {
    const r = await fetch('/api/catalog?scanner=land')
    const j = await r.json()
    return (j.scanners as { implemented: boolean }[]).filter((s) => s.implemented).length
  })
  expect(built).toBeGreaterThanOrEqual(3)
  await expect(page.locator('.lib-plate')).toHaveCount(built)

  await launchScanner(page, 'Land')
  await drawSite(page)

  // The report identifies the site it is about.
  await expect(page.locator('.ovw-coverage')).toContainText(/\d+ of \d+ factors assessed/)

  // Every reporting surface renders. These are separate code paths — a radar,
  // a findings list, a virtualised table, a chart stack and a provenance
  // list — and a crash in any one of them is invisible from the overview.
  for (const tab of ['Radar', 'Findings', 'Table', 'Charts', 'Sources']) {
    await openTab(page, tab)
    await expect(page.locator('.panel-body')).toBeVisible()
  }

  expect(guard.errors, guard.errors.join('\n')).toEqual([])
})

test('an unknown URL gets the 404 page, not an empty shell', async ({ page }) => {
  await page.goto('/no-such-page')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.locator('body')).toContainText(/not found/i)
  // And a way back, so the 404 is a junction rather than a dead end.
  await expect(page.getByRole('link', { name: /home|site scanner/i }).first()).toBeVisible()
})
