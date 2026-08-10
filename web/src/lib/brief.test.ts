import { describe, expect, it } from 'vitest'
import {
  briefHtml, coverageLine, escapeHtml, findingNumber, formatDate, siteLine,
} from './brief'
import type { Brief } from '../types'

/**
 * The Brief leaves the product, so these tests are about what survives the
 * trip. A screen can be clarified in conversation; a document cannot, and the
 * failure mode is a qualification that was on screen and is not on paper.
 */

function brief(over: Partial<Brief> = {}): Brief {
  return {
    sections: ['site', 'coverage', 'findings', 'historical', 'gaps', 'log', 'methodology'],
    site: {
      name: 'Manor Farm, parcel 3', area_ha: 155.16,
      centroid: { lng: -0.572, lat: 51.239 },
      assessed_at: '2026-08-10T14:00:00+00:00',
    },
    coverage: {
      assessed: 1, relevant: 24, not_assessed: 23, flagged: 1, clear: 0,
      informational: 1, not_loaded: 13, no_live_source: 10,
      note: 'Coverage is how much of this site we were able to look at — not how good the site is.',
    },
    findings: [{
      factor: 'ndvi', name: 'NDVI (vegetation vigour)', severity: 'medium',
      findings: [{ text: 'Vegetation vigour has declined 23%.', threshold: '20% decline',
                   rule: 'Historical vegetation decline', method: 'hist-1' }],
      established: ['Vegetation vigour has declined 23%.'],
      not_established: ['It is not evidence of ecological degradation.'],
      investigations: ['Preliminary ecological appraisal'],
      source: {
        publisher: 'Copernicus / ESA', endpoint: 'earthengine.googleapis.com',
        dataset: 'Sentinel-2', licence: 'CC BY-SA 3.0 IGO', attribution: '',
        clearance: 'conditional', runtime: 'verified', kind: 'earth-engine',
      },
    }],
    informational: [],
    historical: [{
      name: 'Vegetation vigour', state: 'flagged', change_pct: -23,
      baseline: 0.61, recent: 0.47, baseline_years: [2017, 2018, 2019],
      recent_years: [2023, 2024, 2025], years_usable: 9, years_total: 15,
      method: 'hist-1',
    }],
    gaps: [{ reason: 'demo_data', label: 'No live source — demo data cannot support a finding',
             count: 10, factors: ['Bare soil index'] }],
    log: [{ factor: 'ndvi', name: 'NDVI (vegetation vigour)', source: 'Copernicus / ESA',
            endpoint: 'earthengine.googleapis.com', status: 'assessed', verified: true,
            at: '2026-08-10T14:00:00+00:00' }],
    methodology: {
      historical: { version: 'hist-1' },
      attributions: ['Contains modified Copernicus Sentinel data 2026'],
      limits: 'Contour reporting thresholds are product-defined.',
    },
    principle: 'A clear result means we checked. An empty result means we could not.',
    ...over,
  }
}

// ---------------------------------------------------------------------------
// What must survive onto paper
// ---------------------------------------------------------------------------
describe('the claim boundary reaches the document', () => {
  it('prints what a finding does not establish, beside what it does', () => {
    const html = briefHtml(brief())
    expect(html).toContain('What this establishes')
    expect(html).toContain('What this does not establish')
    expect(html).toContain('not evidence of ecological degradation')
  })

  it('carries the principle, because the reader never saw the app', () => {
    expect(briefHtml(brief())).toContain('A clear result means we checked')
  })

  it('carries the coverage note next to the coverage numbers', () => {
    expect(briefHtml(brief())).toContain('not how good the site is')
  })

  it('carries attribution, which is a licence condition and not a courtesy', () => {
    expect(briefHtml(brief())).toContain('Contains modified Copernicus Sentinel data')
  })
})

describe('an empty findings list', () => {
  it('never reads as "no issues found"', () => {
    // With most of the catalogue generated, an empty list far more often means
    // nothing could be checked than that nothing is there — and this is the
    // section a reader skims first.
    const html = briefHtml(brief({ findings: [] }))
    expect(html).toContain('evidence that could be read')
    expect(html).toContain('See evidence gaps below')
    expect(html.toLowerCase()).not.toContain('no issues')
    expect(html.toLowerCase()).not.toContain('all clear')
  })
})

// ---------------------------------------------------------------------------
// Layout follows the server's editorial order
// ---------------------------------------------------------------------------
describe('section order', () => {
  it('puts coverage before findings', () => {
    const html = briefHtml(brief())
    expect(html.indexOf('Evidence coverage')).toBeLessThan(html.indexOf('Key findings'))
  })

  it('follows the server list rather than the order of calls here', () => {
    // The order is an editorial decision the backend owns and states its
    // reasoning for. A section the server omits does not appear.
    const html = briefHtml(brief({ sections: ['site', 'coverage'] }))
    expect(html).toContain('Evidence coverage')
    expect(html).not.toContain('Key findings')
    expect(html).not.toContain('Assessment log')
  })
})

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------
describe('formatting', () => {
  it('states both halves of coverage', () => {
    expect(coverageLine(brief())).toBe('1 of 24 factors assessed · 23 not assessed')
  })

  it('never prints a county it cannot source', () => {
    expect(siteLine(brief())).toBe('155.16 ha · 51.2390, -0.5720')
  })

  it('numbers findings so one can be named in an email', () => {
    expect(findingNumber(0)).toBe('01')
    expect(findingNumber(11)).toBe('12')
  })

  it('handles a missing or malformed date without printing "Invalid Date"', () => {
    expect(formatDate('')).toBe('')
    expect(formatDate('not-a-date')).toBe('')
  })

  it('escapes site names, because this document is printed and mailed', () => {
    expect(escapeHtml('<script>alert(1)</script>'))
      .toBe('&lt;script&gt;alert(1)&lt;/script&gt;')
    const html = briefHtml(brief({
      site: { ...brief().site, name: '<img src=x onerror=alert(1)>' },
    }))
    expect(html).not.toContain('<img src=x')
  })
})
