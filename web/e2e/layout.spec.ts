import { expect, test } from '@playwright/test'
import { drawSite, launchScanner, openLibrary, openTab, overflowsHorizontally } from './helpers'

/**
 * Regression cover for the first of the two defects found by hand.
 *
 * `.panel-body` is `overflow: hidden`, so every tab must supply its own
 * scroller. The overview did not, and 820px of content sat inside a 684px box:
 * the evidence-gaps section — the part of the screen the product's whole
 * argument rests on — could not be reached at 900px tall. Nothing failed. It
 * simply was not there.
 *
 * The rule is tested rather than the instance. Asserting "the overview
 * scrolls" would pass again the next time a tab is added without a scroller;
 * asserting "any tab whose content overflows must be scrollable" does not.
 */

const PUBLIC_PAGES = [
  '/', '/scanners', '/scanners/land', '/scanners/habitat',
  '/about', '/case-studies', '/contact', '/request-a-site-scan', '/privacy',
]

test.describe('no page scrolls sideways', () => {
  for (const path of PUBLIC_PAGES) {
    test(`public page ${path}`, async ({ page }) => {
      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      expect(await overflowsHorizontally(page), `${path} overflows horizontally`).toBe(false)
    })
  }

  test('the scanner library', async ({ page }) => {
    await openLibrary(page)
    expect(await overflowsHorizontally(page)).toBe(false)
  })
})

test('every report tab whose content overflows can be scrolled', async ({ page }) => {
  await openLibrary(page)
  await launchScanner(page, 'Land')
  await drawSite(page)

  for (const tab of ['Overview', 'Radar', 'Findings', 'Table', 'Charts', 'Sources']) {
    await openTab(page, tab)

    // Give the tab a beat to lay out — the virtualised table and the chart
    // stack both measure themselves after paint.
    await page.waitForTimeout(400)

    const clipped = await page.evaluate(() => {
      const body = document.querySelector('.panel-body') as HTMLElement | null
      if (!body) return 'no panel body'

      // The failure mode is not an element overflowing *itself* — it is an
      // element taller than the `overflow: hidden` box it sits in, whose
      // surplus is therefore painted nowhere and reachable by nothing. So the
      // comparison is against the panel's visible height, not the child's own.
      const scrolls = (el: HTMLElement) => {
        const o = getComputedStyle(el).overflowY
        return (o === 'auto' || o === 'scroll') && el.scrollHeight > el.clientHeight
      }
      const canScroll = (el: HTMLElement) =>
        scrolls(el) || Array.from(el.querySelectorAll<HTMLElement>('*')).some(scrolls)

      for (const child of Array.from(body.children) as HTMLElement[]) {
        const height = child.getBoundingClientRect().height
        const spare = height - body.clientHeight
        if (spare <= 1) continue
        if (canScroll(child)) continue
        return `${child.className || child.tagName} is ${Math.round(height)}px tall in a `
          + `${body.clientHeight}px panel — ${Math.round(spare)}px is unreachable`
      }
      return null
    })

    expect(clipped, `${tab}: ${clipped}`).toBeNull()
  }

  expect(await overflowsHorizontally(page)).toBe(false)
})
