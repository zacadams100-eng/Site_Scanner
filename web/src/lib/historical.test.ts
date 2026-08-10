import { describe, expect, it } from 'vitest'
import {
  changeText, coverageText, findingClass, findingLabel, orderedEntries,
  periodText, unavailableReason,
} from './historical'
import type { HistoricalEntry } from '../types'

/**
 * EM11, proven rather than claimed.
 *
 * A component that "contains no business logic" is easy to assert and hard to
 * demonstrate. These functions are the whole of the historical panel's
 * decision-making, so feeding them a payload whose numbers contradict its
 * state settles it: if the label follows the state, the UI has no opinion.
 */

function entry(over: Partial<HistoricalEntry> = {}): HistoricalEntry {
  return {
    id: 'vegetation',
    name: 'Vegetation vigour',
    factor: 'ndvi',
    rule: 'historical_vegetation_decline',
    rule_meta: {
      rule: 'Historical vegetation decline',
      threshold_display: '≥ 20% decline',
      threshold_type: 'Contour reporting threshold',
      threshold_status: 'product-defined; not a regulatory or scientific standard',
      purpose: 'Identifies changes large enough to warrant professional investigation.',
      method_version: 'hist-1',
    },
    available: true,
    metric: {
      baseline: 0.61, recent: 0.47, change: -0.14, change_pct: -22.9,
      change_type: 'relative', baseline_years: [2011, 2012, 2013],
      recent_years: [2024, 2025, 2026], years_usable: 16, years_total: 16,
      year_coverage: 1, observation_coverage: 1, method_version: 'hist-1',
      meets_minimum_evidence: true, shortfall: '', source: 'earth-engine',
      real: true, season: [4, 5, 6, 7, 8, 9],
    },
    finding: { state: 'flagged', reason: null },
    ...over,
  } as HistoricalEntry
}

describe('the UI follows the state, never the number', () => {
  it('renders every state the server can send', () => {
    expect(findingLabel(entry({ finding: { state: 'flagged', reason: null } })))
      .toBe('Flagged')
    expect(findingLabel(entry({ finding: { state: 'clear', reason: null } })))
      .toBe('Checked · clear')
    expect(findingLabel(entry({ finding: { state: 'informational', reason: null } })))
      .toBe('Informational')
    expect(findingLabel(entry({ finding: { state: 'not_assessed', reason: 'no_data' } })))
      .toBe('Not assessed')
  })

  it('renders "clear" for a −45% change when the server said clear', () => {
    // The test that settles EM11 for this panel. −45% is "obviously" a flag,
    // and noticing that is exactly what a UI must not do: the threshold might
    // have changed, the evidence might have been insufficient, the rule might
    // not apply to this metric family. Only the server knows.
    const contradictory = entry({
      metric: { ...entry().metric!, change_pct: -45, change: -0.28 },
      finding: { state: 'clear', reason: null },
    })
    expect(findingLabel(contradictory)).toBe('Checked · clear')
    expect(findingClass(contradictory)).toBe('is-clear')
  })

  it('renders "flagged" for a +2% change when the server said flagged', () => {
    // The mirror. A tiny positive change is "obviously" not a flag either.
    const contradictory = entry({
      metric: { ...entry().metric!, change_pct: 2, change: 0.01 },
      finding: { state: 'flagged', reason: null },
    })
    expect(findingLabel(contradictory)).toBe('Flagged')
  })

  it('renders "not assessed" even when a full metric is present', () => {
    // The sneak-through, at the render layer. The numbers exist and look
    // conclusive; the server said the evidence was insufficient.
    const e = entry({
      finding: { state: 'not_assessed', reason: 'no_data',
                 text: 'Not assessed — 2 usable years; 6 required.' },
    })
    expect(findingLabel(e)).toBe('Not assessed')
    expect(unavailableReason(e)).toContain('2 usable years')
  })

  it('treats an unknown state as not assessed rather than guessing', () => {
    const e = entry({ finding: { state: 'sideways' as never, reason: null } })
    expect(findingLabel(e)).toBe('Not assessed')
  })

  it('treats a missing finding as not assessed', () => {
    expect(findingLabel(entry({ finding: null as never }))).toBe('Not assessed')
  })
})

describe('reasons come from the server', () => {
  it('uses the server sentence verbatim when there is one', () => {
    const e = entry({
      finding: { state: 'not_assessed', reason: 'demo_data',
                 text: 'Not assessed — the data behind it is generated.' },
    })
    expect(unavailableReason(e)).toBe(
      'Not assessed — the data behind it is generated.')
  })

  it('says the layer is absent when it was never loaded', () => {
    const e = entry({ available: false, metric: null,
                      finding: { state: 'not_assessed', reason: 'not_selected' } })
    expect(unavailableReason(e)).toContain('not in the report')
  })

  it('says nothing for a state that is not "not assessed"', () => {
    expect(unavailableReason(entry())).toBe('')
  })
})

describe('formatting only', () => {
  it('signs a relative change', () => {
    expect(changeText(entry())).toBe('-22.9%')
    expect(changeText(entry({
      metric: { ...entry().metric!, change_pct: 12.4 },
    }))).toBe('+12.4%')
  })

  it('reports an absolute difference where the baseline was zero', () => {
    // A percentage change from zero is undefined. The server decided that;
    // this only has to not invent one.
    const e = entry({
      metric: { ...entry().metric!, baseline: 0, change: 0.15,
                change_pct: null, change_type: 'absolute' },
    })
    expect(changeText(e)).toBe('+0.150 (absolute)')
    expect(changeText(e)).not.toContain('%')
  })

  it('shows a dash rather than a zero when there is no change to show', () => {
    // "0%" would be a measurement. There isn't one.
    const e = entry({ metric: { ...entry().metric!, change: null,
                                change_pct: null } })
    expect(changeText(e)).toBe('—')
  })

  it('states coverage as observed over total', () => {
    expect(coverageText(entry())).toBe('16 of 16 years observed')
    expect(coverageText(entry({ metric: null }))).toBe('')
  })

  it('formats a period span', () => {
    expect(periodText([2011, 2012, 2013])).toBe('2011–2013')
    expect(periodText([2019])).toBe('2019')
    expect(periodText([])).toBe('—')
    expect(periodText(undefined)).toBe('—')
  })
})

describe('order and completeness', () => {
  it('never reorders entries by severity', () => {
    // Sorting by severity would be the UI deciding which evidence matters.
    const a = entry({ id: 'a', finding: { state: 'clear', reason: null } })
    const b = entry({ id: 'b', finding: { state: 'flagged', reason: null } })
    expect(orderedEntries([a, b]).map((e) => e.id)).toEqual(['a', 'b'])
  })

  it('never drops a clear or unassessed entry', () => {
    // Hiding a clear result is how "we checked" becomes indistinguishable
    // from "we could not look".
    const entries = [
      entry({ id: 'a', finding: { state: 'clear', reason: null } }),
      entry({ id: 'b', finding: { state: 'not_assessed', reason: 'no_data' } }),
      entry({ id: 'c', finding: { state: 'flagged', reason: null } }),
    ]
    expect(orderedEntries(entries)).toHaveLength(3)
  })
})
