import { describe, expect, it } from 'vitest'
import {
  assessedText, attentionRows, changeArrow, changeMagnitude, evidenceRows,
  gapCauses, historicalRows, locationLine, overlapNote,
} from './overview'
import type { Coverage, HistoricalEntry, Investigation } from '../types'

/**
 * The overview is the screen most likely to be read as a verdict, so it is
 * tested for what it must *refuse* to do rather than for what it renders.
 *
 * The load-bearing test is `direction is not a state`. Every other assertion
 * here would survive a careless rewrite; that one fails the moment someone
 * decides a falling number should be drawn in red.
 */

function coverage(over: Partial<Coverage> = {}): Coverage {
  return {
    relevant: 24, assessed: 6, share: 0.25,
    flagged: 2, clear: 3, informational: 1, not_assessed: 18,
    not_selected: 12, generated: 6, verified: 1,
    note: 'Coverage is how much of this site we were able to look at.',
    ...over,
  }
}

function entry(over: Partial<HistoricalEntry> = {}): HistoricalEntry {
  return {
    id: 'vegetation', name: 'Vegetation vigour', factor: 'ndvi',
    rule: 'historical_vegetation_decline', rule_meta: {}, available: true,
    metric: {
      change_pct: -23, change: -0.14, change_type: 'relative',
      baseline: 0.61, recent: 0.47, baseline_years: [2017, 2018, 2019],
      recent_years: [2023, 2024, 2025], years_usable: 9, years_total: 15,
      year_coverage: 0.6, observation_coverage: 0.6,
      meets_minimum_evidence: true, shortfall: '', method_version: 'hist-1',
      real: true, season: [4, 5, 6, 7, 8, 9],
    } as HistoricalEntry['metric'],
    finding: { state: 'flagged', reason: null },
    ...over,
  }
}

// ---------------------------------------------------------------------------
// EM11 — the overview reads states, it never reaches one
// ---------------------------------------------------------------------------
describe('direction is not a state', () => {
  it('draws a steep decline the engine called clear as clear', () => {
    // The trap this whole module is shaped around. −45% is "obviously" bad,
    // and a summary screen is exactly where someone adds `change < 0 && 'red'`.
    // The threshold may have moved, the evidence may have been insufficient,
    // the rule may not apply — only the server knows.
    const [row] = historicalRows([entry({
      metric: { ...entry().metric!, change_pct: -45 },
      finding: { state: 'clear', reason: null },
    })])

    expect(row.arrow).toBe('↓')          // the number fell: formatting
    expect(row.stateLabel).toBe('Checked · clear')   // the engine's verdict
    expect(row.stateClass).toBe('is-clear')
  })

  it('draws a rise the engine flagged as flagged', () => {
    // The mirror. A rising built-surface index is a flag; a rising NDVI is
    // usually not. Direction carries no meaning without the rule.
    const [row] = historicalRows([entry({
      metric: { ...entry().metric!, change_pct: 12 },
      finding: { state: 'flagged', reason: null },
    })])

    expect(row.arrow).toBe('↑')
    expect(row.stateClass).toBe('is-flagged')
  })

  it('gives a metric with no finding the not-assessed state, not a guess', () => {
    const [row] = historicalRows([entry({ finding: null })])
    expect(row.stateLabel).toBe('Not assessed')
    expect(row.stateClass).toBe('is-not_assessed')
  })

  it('shows no arrow where nothing moved or nothing was measured', () => {
    expect(changeArrow(entry({ metric: { ...entry().metric!, change_pct: 0 } }))).toBe('')
    expect(changeArrow(entry({ metric: null }))).toBe('')
  })

  it('does not state the direction twice', () => {
    // "↓ -23.0%" reads as a double negative. The arrow carries the sign here;
    // changeText keeps its own sign for the historical panel, which has no
    // arrow.
    const [row] = historicalRows([entry()])
    expect(row.arrow).toBe('↓')
    expect(row.change).toBe('23.0%')
    expect(changeMagnitude(entry())).toBe('23.0%')
  })

  it('keeps the signed text when there is no arrow to carry it', () => {
    const [row] = historicalRows([entry({
      metric: { ...entry().metric!, change_pct: 0 },
    })])
    expect(row.arrow).toBe('')
    expect(row.change).toBe('0.0%')
  })
})

// ---------------------------------------------------------------------------
// EM7 / EM10 — counts never travel without their coverage
// ---------------------------------------------------------------------------
describe('counts and coverage', () => {
  it('lists the four states in a fixed order, not by size', () => {
    // Sorting by count would put the largest number first and quietly turn a
    // coverage strip into a ranking of its own states.
    const rows = evidenceRows(coverage({ flagged: 1, clear: 40 }))
    expect(rows.map((r) => r.key))
      .toEqual(['flagged', 'clear', 'informational', 'not_assessed'])
  })

  it('states coverage as a fraction of what was relevant', () => {
    expect(assessedText(coverage())).toBe('6 of 24 factors assessed')
  })

  it('reconciles assessed against not assessed, which is the real partition', () => {
    // The four states are NOT a partition, and an earlier version of this test
    // asserted they were — it passed only because the fixture numbers happened
    // to sum. `flagged` and `informational` are independent factor sets in
    // radar._coverage and a factor can be in both, so the arithmetic that
    // actually holds is this one.
    const c = coverage()
    expect(c.assessed + c.not_assessed).toBe(c.relevant)
  })

  it('explains the overlap when the four counts exceed the total', () => {
    // The real payload does this: one NDVI series carrying a decline flag and
    // a mean-vigour reading is counted in `flagged` and in `informational`.
    const c = coverage({ relevant: 24, assessed: 1, flagged: 1, clear: 0,
                         informational: 1, not_assessed: 23 })
    expect(evidenceRows(c).reduce((n, r) => n + r.count, 0)).toBe(25)
    expect(overlapNote(c)).toContain('overlap')
    expect(overlapNote(c)).toMatch(/^1 factor carries/)
  })

  it('stays quiet when the states do not overlap', () => {
    // A note that is always on screen is furniture and stops being read.
    expect(overlapNote(coverage({ assessed: 6, flagged: 2, clear: 3,
                                  informational: 1 }))).toBe('')
  })

  it('survives a missing coverage block without inventing numbers', () => {
    expect(evidenceRows(undefined).every((r) => r.count === 0)).toBe(true)
    expect(assessedText(undefined)).toBe('')
  })
})

// ---------------------------------------------------------------------------
// The gap split — one is a click, the other is a wall
// ---------------------------------------------------------------------------
describe('evidence gaps', () => {
  it('separates a fixable gap from a permanent one', () => {
    const causes = gapCauses(coverage({ not_selected: 12, generated: 6 }))
    expect(causes.map((c) => c.key)).toEqual(['not_selected', 'generated'])
    expect(causes[0].count).toBe(12)
    expect(causes[1].text).toContain('demo data')
  })

  it('omits a cause with nothing in it rather than printing a zero', () => {
    expect(gapCauses(coverage({ not_selected: 0, generated: 4 })).map((c) => c.key))
      .toEqual(['generated'])
  })
})

// ---------------------------------------------------------------------------
// Ordering is the engine's, not the screen's
// ---------------------------------------------------------------------------
describe('what needs attention', () => {
  it('keeps the server ranking exactly', () => {
    // The promotion rule depends on which factors the flags rest on. A UI
    // re-sort would be a second opinion about priority.
    const given = [
      { id: 'b', name: 'B', blurb: '', priority: 'medium', why: ['x'], why_text: [] },
      { id: 'a', name: 'A', blurb: '', priority: 'high', why: ['y'], why_text: [] },
    ] as Investigation[]
    expect(attentionRows(given).map((i) => i.id)).toEqual(['b', 'a'])
  })

  it('has nothing to show when no flag raised anything', () => {
    expect(attentionRows([])).toEqual([])
    expect(attentionRows(undefined)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// The header line
// ---------------------------------------------------------------------------
describe('location line', () => {
  it('states area and centroid', () => {
    expect(locationLine(24.6, { lng: -0.57, lat: 51.24 }))
      .toBe('24.6 ha · 51.2400, -0.5700')
  })

  it('never invents an administrative area', () => {
    // A briefing header wants "24.6 ha · Surrey". The only source of a county
    // in this product is an explicit postcodes.io search; a drawn shape has
    // none, and deriving one from a coordinate would be a guess printed where
    // a reader trusts it most.
    const line = locationLine(24.6, { lng: -0.57, lat: 51.24 })
    expect(line).not.toMatch(/[A-Z][a-z]+shire|Surrey|County/)
  })

  it('drops what it does not have instead of printing a placeholder', () => {
    expect(locationLine(undefined, undefined)).toBe('')
    expect(locationLine(24.6, undefined)).toBe('24.6 ha')
  })
})
