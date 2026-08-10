import { describe, expect, it } from 'vitest'
import {
  SECTIONS, allVerified, findEntry, humanKey, methodsUsed, priorityClass,
  priorityLabel, raisedSummary,
} from './investigation'
import type { InvestigationWorkspaceEntry } from '../types'

/**
 * The load-bearing test here is the coastal one.
 *
 * It renders an investigation from a domain this codebase does not implement,
 * assembled entirely from fabricated metadata. If it ever needs a change to
 * `lib/investigation.ts` to pass, the workspace has grown a domain assumption
 * and the diff says exactly which one.
 */

/** A coastal investigation. Nothing here exists in the catalogue or in any
 *  rule — the subject is a shoreline, not a site. */
function coastal(): InvestigationWorkspaceEntry {
  return {
    id: 'coastal_process_study',
    name: 'Coastal process study',
    blurb: 'Sediment transport, wave climate and the retreat record.',
    next_step: 'Commission a coastal process study covering the frontage.',
    priority: 'high',
    raised_by: [{
      id: 'shoreline_retreat', rule: 'Shoreline retreat',
      text: 'Mean high water has retreated 14 m since the baseline period.',
      severity: 'high', threshold: '10 m retreat (Contour reporting threshold)',
      threshold_type: 'Contour reporting threshold',
      threshold_status: 'product-defined; not a regulatory standard',
      method: 'coast-1', factors: ['shoreline_position'],
    }],
    established: ['Mean high water has retreated 14 m.'],
    not_established: ['It is not evidence of accelerating erosion.'],
    evidence: [{
      factor: 'shoreline_position', name: 'Mean high water position',
      state: 'flagged', publisher: 'Copernicus / ESA',
      endpoint: 'earthengine.googleapis.com',
      dataset: 'Sentinel-2 Surface Reflectance', licence: 'CC BY-SA 3.0 IGO',
      attribution: 'Contains modified Copernicus Sentinel data 2026',
      runtime: 'verified', assessed_at: '2026-08-10T00:00:00+00:00',
      methods: ['coast-1'],
      measurements: [{ rule: 'shoreline_retreat', rule_name: 'Shoreline retreat',
                       threshold: '10 m retreat', evidence: { retreat_m: -14 } }],
    }],
  }
}

describe('the workspace renders a domain it has never seen', () => {
  it('carries a coastal investigation through every helper', () => {
    const e = coastal()
    expect(priorityLabel(e)).toBe('high')
    expect(priorityClass(e)).toBe('is-high')
    expect(raisedSummary(e)).toBe('Raised by 1 finding')
    expect(methodsUsed(e)).toEqual(['coast-1'])
    expect(allVerified(e)).toBe(true)
  })

  it('has no section heading that names a thing in the world', () => {
    // The structure of a professional's question is domain-neutral. The
    // moment a heading says "site" or "parcel", the screen stops serving
    // every other domain.
    const headings = SECTIONS.map((s) => s.title.toLowerCase()).join(' ')
    for (const word of ['site', 'land', 'parcel', 'development', 'planning',
                        'property', 'coast', 'habitat', 'mine']) {
      expect(headings, `heading names a domain: ${word}`).not.toContain(word)
    }
  })

  it('formats an unfamiliar measurement key without a lookup table', () => {
    // A per-domain lookup would be the coupling this module avoids.
    expect(humanKey('retreat_m')).toBe('Retreat m')
    expect(humanKey('change_pct')).toBe('Change pct')
  })
})

describe('reading, never deriving', () => {
  it('takes the engine\'s priority rather than ranking again', () => {
    expect(priorityLabel({ ...coastal(), priority: 'medium' })).toBe('medium')
    expect(priorityLabel({ ...coastal(), priority: '' })).toBe('unranked')
  })

  it('says "1 finding", not "1 findings"', () => {
    // In the screen where a professional decides whether to trust the output,
    // a grammar slip reads as unproofed software.
    expect(raisedSummary(coastal())).toContain('1 finding')
    expect(raisedSummary({ ...coastal(),
      raised_by: [...coastal().raised_by, ...coastal().raised_by] }))
      .toContain('2 findings')
  })

  it('reports verification as a fact about the evidence', () => {
    const partial = coastal()
    partial.evidence = [{ ...partial.evidence[0], runtime: 'written' }]
    expect(allVerified(partial)).toBe(false)
    expect(allVerified({ ...coastal(), evidence: [] })).toBe(false)
  })

  it('finds nothing without inventing an entry', () => {
    expect(findEntry([coastal()], 'missing')).toBeNull()
    expect(findEntry(undefined, 'coastal_process_study')).toBeNull()
    expect(findEntry([coastal()], null)).toBeNull()
    expect(findEntry([coastal()], 'coastal_process_study')?.name)
      .toBe('Coastal process study')
  })
})
