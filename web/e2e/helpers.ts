import { expect, type Page } from '@playwright/test'

/**
 * Shared steps for driving the application.
 *
 * Kept in one place so a selector change costs one edit rather than four, and
 * so the specs below read as the journey a user takes rather than as a list of
 * clicks.
 */

/** Console noise that says nothing about this application's health.
 *
 *  The basemap fetches vector tiles from a third party. In a sandbox without
 *  egress those fail, and the app handles it — the bundled basemap covers the
 *  same zooms. Counting that as a defect would make the suite fail for a
 *  reason the code cannot fix, which is how a suite gets ignored. Anything
 *  from our own origin still counts. */
const IGNORED = [
  /openfreemap|tiles\.openfreemap/i,
  /ERR_(NAME_NOT_RESOLVED|INTERNET_DISCONNECTED|PROXY|TUNNEL|CONNECTION|BLOCKED)/i,
  /Failed to load resource.*\b(4\d\d|5\d\d)\b.*openfreemap/i,
  /net::ERR_/i,
  /\[vite\]/i,
  /Download the React DevTools/i,
]

export interface ConsoleGuard {
  /** Everything worth failing a test over: uncaught exceptions and genuine
   *  console errors, third-party network noise excluded. */
  errors: string[]
}

/**
 * Records console errors and uncaught exceptions for the life of the page.
 *
 * Attach before the first navigation — listeners registered after a `goto`
 * miss everything that happened during it, which is precisely when a broken
 * app is loudest.
 */
export function watchConsole(page: Page): ConsoleGuard {
  const guard: ConsoleGuard = { errors: [] }
  const keep = (text: string) => !IGNORED.some((re) => re.test(text))
  page.on('console', (m) => {
    if (m.type() === 'error' && keep(m.text())) guard.errors.push(`console: ${m.text()}`)
  })
  page.on('pageerror', (e) => {
    if (keep(String(e))) guard.errors.push(`pageerror: ${e}`)
  })
  return guard
}

/**
 * Whether the document scrolls sideways.
 *
 * A page wider than its own viewport is nearly always a layout escape — a
 * fixed width, an unwrapped table, a padding that survives a media query. One
 * pixel of slack absorbs sub-pixel rounding, which browsers do produce and
 * which no user can see.
 */
export async function overflowsHorizontally(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
}

/** Open the application and wait for the scanner library to be populated from
 *  the catalogue, not merely for the route to render. */
export async function openLibrary(page: Page): Promise<void> {
  await page.goto('/app')
  await expect(page.locator('.lib-plate').first()).toBeVisible({ timeout: 30_000 })
}

/** Launch a scanner from the library and wait for its workspace. */
export async function launchScanner(page: Page, name: 'Land' | 'Ecology' | 'Water' | 'Planning'): Promise<void> {
  await page.getByRole('button', { name: `Open the ${name} scanner` }).click()
  await expect(page.locator('.stage')).toBeVisible()
  await expect(page.locator('.brand-scanner')).toHaveText(name)
}

/**
 * Draw a rectangle on the map and wait for the report to arrive.
 *
 * Drags across the middle of the stage: the exact coordinates do not matter
 * because the backend answers for any geometry inside England, and the map is
 * centred there on load.
 */
export async function drawSite(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Rectangle', exact: true }).click()
  const box = await page.locator('.stage').boundingBox()
  if (!box) throw new Error('map stage has no box — the map did not mount')
  await page.mouse.move(box.x + box.width * 0.38, box.y + box.height * 0.34)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * 0.62, box.y + box.height * 0.56, { steps: 14 })
  await page.mouse.up()
  // The report replaces the "start here" placeholder once the series return.
  await expect(page.locator('.ovw-coverage')).toBeVisible({ timeout: 45_000 })
}

/** Switch report tabs and wait for the panel to settle. */
export async function openTab(page: Page, name: string): Promise<void> {
  await page.getByRole('tab', { name }).click()
  await expect(page.getByRole('tab', { name })).toHaveAttribute('aria-selected', 'true')
}
