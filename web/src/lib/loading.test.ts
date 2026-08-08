import { describe, expect, it } from 'vitest'
import type { Factor } from '../types'
import {
  MAX_ROWS, SLOW_AFTER_S, explainWait, selectedFactors, waitingOn,
} from './loading'

/**
 * What the app says while it is working.
 *
 * The old loading state narrated internal stages on a timer — "Rolling months
 * into years…" arrived at 2.5 seconds whether or not any months were being
 * rolled. It was a small, grey, entirely uncontroversial lie, and it is
 * exactly the kind this project refuses everywhere else.
 *
 * So the replacement only says things the client can actually know: which
 * layers were requested, which of them are real, and which host each real one
 * reaches. These tests exist to keep it that way — most of them are about what
 * the copy must *not* claim.
 */

const factor = (id: string, over: Partial<Factor> = {}): Factor => ({
  id,
  name: id,
  base: 'b',
  group: 'g',
  unit: '',
  kind: 'continuous',
  cadence: 'monthly',
  lo: 0,
  hi: 1,
  derived: false,
  note: '',
  ...over,
})

const live = (id: string, endpoint: string) =>
  factor(id, {
    real: true,
    provenance: { source: 'X', endpoint, status: 'written' } as Factor['provenance'],
  })


describe('explainWait', () => {
  it('does not claim nothing is being fetched', () => {
    // The first draft said "so nothing is being fetched" for an all-demo
    // selection. The request is still in flight — saying otherwise while the
    // user watches a spinner is the small kind of wrong that costs trust in
    // the large kind.
    const text = explainWait([factor('a'), factor('b')])!
    expect(text).not.toMatch(/nothing is being fetched/i)
    expect(text).toContain('demo data')
  })

  it('counts the layers it is talking about', () => {
    expect(explainWait([factor('a'), factor('b'), factor('c')]))
      .toContain('All 3 layers')
  })

  it('uses the singular for one layer', () => {
    expect(explainWait([factor('a')])).toBe(
      'This layer is demo data, generated on the server.')
  })

  it('says when everything is a live source', () => {
    const text = explainWait([live('a', 'h1'), live('b', 'h2')])!
    expect(text).toBe('All 2 are live sources, each one an upstream fetch.')
  })

  it('names the split, and blames the right half for the wait', () => {
    const text = explainWait([factor('a'), factor('b'), live('c', 'h')])!
    expect(text).toBe(
      '1 of 3 is a live source, and that is the one taking the time.')
  })

  it('agrees in number when several are live', () => {
    const text = explainWait([factor('a'), live('b', 'h'), live('c', 'h')])!
    expect(text).toBe(
      '2 of 3 are live sources, and those are the ones taking the time.')
  })

  it('says nothing when there is nothing to say', () => {
    expect(explainWait([])).toBeNull()
  })

  /**
   * The rule the whole component is built around. `/api/series` is one POST
   * returning every factor at once, so the client never learns that one layer
   * has landed and another has not. Any word implying otherwise is a guess.
   */
  it('never implies per-factor progress', () => {
    const selections = [
      [factor('a')],
      [factor('a'), live('b', 'h')],
      [live('a', 'h'), live('b', 'h')],
    ]
    const forbidden = /\b(done|complete|completed|finished|loaded|remaining|of \d+ done|progress|\d+%)\b/i
    for (const sel of selections) {
      expect(explainWait(sel) ?? '').not.toMatch(forbidden)
    }
  })
})


describe('waitingOn', () => {
  it('names the hosts rather than describing them', () => {
    // "the data source is slow" is not actionable; the hostname is.
    expect(waitingOn([live('a', 'earthengine.googleapis.com')]))
      .toEqual(['earthengine.googleapis.com'])
  })

  it('deduplicates — four designations behind one host is one host', () => {
    const f = ['a', 'b', 'c', 'd'].map((id) => live(id, 'planning.data.gov.uk'))
    expect(waitingOn(f)).toEqual(['planning.data.gov.uk'])
  })

  it('ignores generated factors, which reach no host at all', () => {
    expect(waitingOn([factor('a'), factor('b')])).toEqual([])
  })

  it('survives a real factor with no provenance recorded', () => {
    expect(waitingOn([factor('a', { real: true })])).toEqual([])
  })
})


describe('selectedFactors', () => {
  it('keeps the order the user chose', () => {
    const all = [factor('a'), factor('b'), factor('c')]
    expect(selectedFactors(['c', 'a'], all).map((f) => f.id)).toEqual(['c', 'a'])
  })

  it('drops an id the catalogue does not know', () => {
    // A permalink saved before a factor was renamed. Rendering `undefined` as
    // a skeleton row would put a blank line in the panel.
    expect(selectedFactors(['a', 'gone'], [factor('a')]).map((f) => f.id))
      .toEqual(['a'])
  })

  it('copes with the catalogue not having loaded', () => {
    expect(selectedFactors(['a'], undefined)).toEqual([])
  })
})


describe('the thresholds', () => {
  it('collapses a long selection rather than drawing a barcode', () => {
    // Twelve factors is the selection cap in store.ts.
    expect(MAX_ROWS).toBeLessThan(12)
    expect(MAX_ROWS).toBeGreaterThan(3)
  })

  it('waits long enough before blaming the upstream', () => {
    // A real Earth Engine query takes seconds. Calling it slow at two would
    // cry wolf on every normal request.
    expect(SLOW_AFTER_S).toBeGreaterThanOrEqual(8)
  })
})
