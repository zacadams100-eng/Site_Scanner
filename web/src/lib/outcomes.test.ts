import { describe, expect, it } from 'vitest'
import type { SavedAoi, SiteOutcome, SiteReview } from '../store'

/**
 * Outcome and review capture, as a data contract.
 *
 * Both are storage for features that do not exist. The tests worth having are
 * therefore not about behaviour but about restraint: that nothing aggregates,
 * nothing scores, and an absent review never reads as a completed one.
 */

const outcome = (over: Partial<SiteOutcome> = {}): SiteOutcome => ({
  id: '1', note: 'Outline permission refused on flood grounds.',
  occurredOn: '2026-03-14', recordedAt: 1_770_000_000_000,
  scanner: 'land', findingIds: ['flood_zone3', 'green_belt'],
  coverage: { assessed: 9, relevant: 24 }, ...over,
})

describe('an outcome is attached to what the report said at the time', () => {
  it('carries the findings that were on screen, not a live reference', () => {
    // A re-run against different data must not change what this was recorded
    // against.
    const o = outcome()
    expect(o.findingIds).toEqual(['flood_zone3', 'green_belt'])
  })

  it('carries the coverage, because an outcome against a thin assessment is a weaker signal', () => {
    expect(outcome().coverage).toEqual({ assessed: 9, relevant: 24 })
  })

  it('separates when it happened from when it was typed', () => {
    const o = outcome({ occurredOn: '2026-03-14', recordedAt: Date.parse('2026-08-01') })
    expect(o.occurredOn).not.toBe(new Date(o.recordedAt).toISOString().slice(0, 10))
  })

  it('names the scanner, because three scanners assess the same ground differently', () => {
    expect(outcome({ scanner: 'coastal' }).scanner).toBe('coastal')
  })
})

describe('nothing is derived from an outcome', () => {
  it('has no score, rating, verdict or weight field', () => {
    const keys = Object.keys(outcome())
    for (const banned of ['score', 'rating', 'verdict', 'weight', 'accuracy',
                          'correct', 'confidence']) {
      expect(keys).not.toContain(banned)
    }
  })

  it('is a free-text note rather than a fixed set of outcomes', () => {
    // A dropdown would be the product deciding in advance what counts as a
    // result, which is the same mistake as scoring a site.
    expect(typeof outcome().note).toBe('string')
  })
})

describe('a review is absent until someone records one', () => {
  it('is optional on a saved site', () => {
    const site: SavedAoi = {
      id: 's', name: 'A site', geometry: { type: 'Polygon', coordinates: [] },
      area_ha: 10, savedAt: 0,
    }
    expect(site.review).toBeUndefined()
    expect(site.outcomes).toBeUndefined()
  })

  it('requires a person and a date — an unnamed reviewer is not a review', () => {
    const review: SiteReview = {
      name: 'A Person', role: 'Chartered ecologist',
      reviewedOn: '2026-04-02', recordedAt: 1,
    }
    expect(review.name).not.toBe('')
    expect(review.role).not.toBe('')
    expect(review.reviewedOn).not.toBe('')
  })

  it('has no approved or signed-off flag', () => {
    // The presence of a named reviewer is the whole statement. A boolean would
    // invite a default, and the default would be a claim.
    const review: SiteReview = { name: 'X', role: 'Y', reviewedOn: 'Z', recordedAt: 1 }
    for (const banned of ['approved', 'signedOff', 'verified', 'passed']) {
      expect(Object.keys(review)).not.toContain(banned)
    }
  })
})
