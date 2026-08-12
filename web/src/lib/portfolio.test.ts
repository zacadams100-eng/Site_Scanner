import { describe, expect, it } from 'vitest'
import type { PortfolioRadar, PortfolioRow } from '../types'
import {
  ATTENTION_NOTE, attentionOf, groupRows, lastAssessed, radarTiles,
} from './portfolio'

/**
 * The portfolio view's display rules.
 *
 * A portfolio mistake is not visible the way a single-site mistake is. A
 * professional reading one report sees the gaps; a reader of a portfolio sees a
 * number, applies it to a thousand sites, and has no way to check it.
 *
 * So these tests are about the ways an aggregate view misleads: burying what
 * was never scanned, making a gap look quieter than a finding, letting a clear
 * result read as a sound site, or turning a partition into a rank.
 */

const RADAR: PortfolioRadar = {
  sites: 24, sites_assessed: 18, sites_unassessed: 6,
  sites_with_findings: 12, findings: 15, investigations: 15,
  factor_gaps: 103, domain_gaps: 43, evidence_gaps: 146,
  awaiting_review: 12, by_scanner: { land: 1, water: 5 },
  demo_sites: 24, contains_demo_data: true,
}

const row = (over: Partial<PortfolioRow> = {}): PortfolioRow => ({
  site_id: 'site_1', name: 'A field', area_ha: 12, assessed: true,
  scanners: ['land'], findings: 0, investigations: 0, evidence_gaps: 3,
  awaiting_review: false, last_assessed: '2026-08-01T00:00:00Z',
  is_demo: false, source: 'drawn', ...over,
})

describe('the radar puts what is not known before what is', () => {
  it('shows never-scanned second, ahead of any finding count', () => {
    // The same editorial rule the Brief follows for coverage-before-findings.
    // A reader who meets "12 with findings" before "6 never scanned" has
    // already formed a view — and at this scale that view gets applied to
    // every site at once.
    const keys = radarTiles(RADAR).map((t) => t.key)
    expect(keys[0]).toBe('sites')
    expect(keys[1]).toBe('unassessed')
    expect(keys.indexOf('unassessed')).toBeLessThan(keys.indexOf('findings'))
  })

  it('says a never-scanned site is unexamined rather than clear', () => {
    const tile = radarTiles(RADAR).find((t) => t.key === 'unassessed')!
    expect(tile.note).toMatch(/not clear/i)
    expect(tile.note).toMatch(/unexamined/i)
  })

  it('gives every tile a note saying what the number does not mean', () => {
    // A large figure is the most quotable thing on the screen and it will be
    // quoted without its heading.
    for (const tile of radarTiles(RADAR)) {
      expect(tile.note.length).toBeGreaterThan(30)
    }
  })

  it('marks the gap tiles so they cannot be styled quieter than the findings', () => {
    const byKey = Object.fromEntries(radarTiles(RADAR).map((t) => [t.key, t]))
    expect(byKey.unassessed.kind).toBe('gap')
    expect(byKey.gaps.kind).toBe('gap')
  })

  it('renders nothing rather than zeroes when there is no radar', () => {
    expect(radarTiles(null)).toEqual([])
    expect(radarTiles(undefined)).toEqual([])
  })

  it('derives no total, average or percentage', () => {
    // Every value on the page is a count the backend supplied. A derived
    // portfolio statistic is acted on across every site at once.
    const values = radarTiles(RADAR).map((t) => t.value)
    for (const v of values) expect(Number.isInteger(v)).toBe(true)
    expect(values).toEqual([24, 6, 12, 15, 146, 12])
  })
})

describe('rows are partitioned, not ranked', () => {
  it('separates has-findings, never-scanned and nothing-flagged', () => {
    expect(attentionOf(row({ findings: 2 }))).toBe('findings')
    expect(attentionOf(row({ assessed: false, scanners: [] }))).toBe('unassessed')
    expect(attentionOf(row())).toBe('quiet')
  })

  it('never puts an unassessed site in the same bucket as a clear one', () => {
    // The founding distinction, at portfolio scale where an empty findings
    // column looks identical for both.
    const groups = groupRows([
      row({ site_id: 'a', assessed: false, scanners: [] }),
      row({ site_id: 'b' }),
    ])
    expect(groups.map((g) => g.attention)).toEqual(['unassessed', 'quiet'])
  })

  it('says a quiet site is not thereby a sound one', () => {
    expect(ATTENTION_NOTE.quiet).toMatch(/not a statement that the site is sound/i)
    expect(ATTENTION_NOTE.quiet).toMatch(/checks that ran/i)
  })

  it('keeps the backend ordering inside a bucket rather than re-sorting', () => {
    // Re-deriving the order in the frontend would be a second opinion about
    // what needs attention.
    const rows = [
      row({ site_id: 'a', name: 'Zebra', findings: 1 }),
      row({ site_id: 'b', name: 'Alpha', findings: 5 }),
    ]
    expect(groupRows(rows)[0].rows.map((r) => r.name)).toEqual(['Zebra', 'Alpha'])
  })

  it('drops an empty bucket rather than rendering an empty heading', () => {
    expect(groupRows([row({ findings: 3 })]).map((g) => g.attention))
      .toEqual(['findings'])
    expect(groupRows([])).toEqual([])
  })
})

describe('a date column never renders a blank', () => {
  it('says Never for a site nothing has looked at', () => {
    // An empty cell in a date column reads as a rendering fault rather than
    // as a fact about the site.
    expect(lastAssessed(row({ assessed: false, last_assessed: '' }))).toBe('Never')
  })

  it('says the date is not recorded rather than showing an invalid one', () => {
    expect(lastAssessed(row({ last_assessed: '' }))).toBe('Date not recorded')
    expect(lastAssessed(row({ last_assessed: 'not a date' }))).toBe('Date not recorded')
  })

  it('formats a real date', () => {
    expect(lastAssessed(row({ last_assessed: '2026-08-01T00:00:00Z' })))
      .toBe('1 Aug 2026')
  })
})
