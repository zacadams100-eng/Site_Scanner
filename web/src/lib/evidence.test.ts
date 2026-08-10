import { describe, expect, it } from 'vitest'
import {
  findEntry, orderedEntries, runtimeLabel, sections, sourceRows, stateClass,
  stateLabel,
} from './evidence'
import type { EvidenceEntry } from '../types'

function entry(over: Partial<EvidenceEntry> = {}): EvidenceEntry {
  return {
    factor: 'ndvi', name: 'NDVI (vegetation vigour)',
    state: 'flagged', reason: null, severity: 'medium',
    findings: [{
      id: 'historical_vegetation_decline', kind: 'flag',
      text: 'Vegetation vigour has declined 23%.', severity: 'medium',
      threshold: '20% decline (Contour reporting threshold)',
      evidence: { change_pct: -23, baseline_period: '2017–2019' },
      rule_meta: { threshold_type: 'Contour reporting threshold' },
    }],
    source: {
      publisher: 'Copernicus / ESA', endpoint: 'earthengine.googleapis.com',
      dataset: 'Sentinel-2 Surface Reflectance', licence: 'CC BY-SA 3.0 IGO',
      attribution: 'Contains modified Copernicus Sentinel data 2026',
      clearance: 'conditional', runtime: 'verified', kind: 'earth-engine',
    },
    investigations: [{ id: 'ecology_survey', name: 'Preliminary ecological appraisal',
                       priority: 'high', why: ['historical_vegetation_decline'] }],
    assessed_at: '2026-08-10T13:00:00+00:00',
    claims: { established: 'Declined 23%.', not_established: 'Not a cause.' },
    ...over,
  }
}

// ---------------------------------------------------------------------------
// EM11 — the explorer renders states, it does not reach them
// ---------------------------------------------------------------------------
describe('state is read, never derived', () => {
  it('labels a steep decline the engine called clear as clear', () => {
    // Same hostile fixture as the historical panel: numbers that contradict
    // the state, and the state wins.
    const e = entry({
      state: 'clear',
      findings: [{ ...entry().findings[0], evidence: { change_pct: -45 } }],
    })
    expect(stateLabel(e)).toBe('Checked · clear')
    expect(stateClass(e)).toBe('is-clear')
  })

  it('names why a factor was not assessed, in the server\'s three causes', () => {
    expect(stateLabel(entry({ state: 'not_assessed', reason: 'no_data' })))
      .toBe('Not assessed · no usable observation')
    expect(stateLabel(entry({ state: 'not_assessed', reason: 'not_selected' })))
      .toBe('Not assessed · not loaded')
    expect(stateLabel(entry({ state: 'not_assessed', reason: 'demo_data' })))
      .toBe('Not assessed · no live source')
  })
})

// ---------------------------------------------------------------------------
// Each state renders a deliberate shape
// ---------------------------------------------------------------------------
describe('sections per state', () => {
  it('gives a flag the full chain: measurement, threshold, investigation', () => {
    const s = sections(entry())
    expect(s).toEqual({ measurement: true, threshold: true, investigation: true })
  })

  it('gives clear a threshold, because why nothing was crossed is the point', () => {
    const s = sections(entry({ state: 'clear', investigations: [] }))
    expect(s.threshold).toBe(true)
    expect(s.investigation).toBe(false)
  })

  it('never shows a threshold for an informational reading', () => {
    // The load-bearing one. An informational finding applies no threshold, and
    // an empty threshold block implies one exists and was met — a fake
    // threshold is exactly what this state must not invent.
    const s = sections(entry({ state: 'informational', investigations: [] }))
    expect(s.threshold).toBe(false)
    expect(s.measurement).toBe(true)
  })

  it('shows neither measurement nor threshold when nothing was measured', () => {
    const s = sections(entry({
      state: 'not_assessed', reason: 'demo_data', findings: [], investigations: [],
    }))
    expect(s.measurement).toBe(false)
    expect(s.threshold).toBe(false)
  })

  it('drives sections from state, not from a populated field', () => {
    // An informational entry that happens to carry a threshold string must
    // still not render a threshold block — otherwise the section grows back
    // the moment an unrelated payload field is non-empty.
    const e = entry({
      state: 'informational',
      findings: [{ ...entry().findings[0], threshold: '20% decline' }],
    })
    expect(sections(e).threshold).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Provenance: four questions, four fields
// ---------------------------------------------------------------------------
describe('source rows', () => {
  it('keeps publisher and endpoint apart', () => {
    // HE1: Sentinel-2 reaches this product *through* Earth Engine. A user told
    // only "Copernicus" would look for the number in the Copernicus Data Space
    // and find a different one.
    const rows = Object.fromEntries(sourceRows(entry()))
    expect(rows.Publisher).toBe('Copernicus / ESA')
    expect(rows.Endpoint).toBe('earthengine.googleapis.com')
    expect(rows.Publisher).not.toBe(rows.Endpoint)
  })

  it('shows all four rows even when a value is missing', () => {
    // "Publisher: —" is a readable statement about what Contour knows. A row
    // that disappears is indistinguishable from one nobody thought to add.
    const rows = sourceRows(entry({
      source: { ...entry().source, publisher: '', licence: '' },
    }))
    expect(rows).toHaveLength(4)
    expect(Object.fromEntries(rows).Publisher).toBe('—')
  })

  it('says what the runtime can actually prove', () => {
    // EM5: a deployment with no credentials implements a factor and can prove
    // none of it.
    expect(runtimeLabel('verified')).toBe('Verified live')
    expect(runtimeLabel('written')).toBe('Implemented, not yet run live')
    expect(runtimeLabel('generated')).toContain('demo data')
    expect(runtimeLabel('not_loaded')).toContain('Not loaded')
    expect(runtimeLabel('anything else')).toBe('Unknown')
  })
})

// ---------------------------------------------------------------------------
// Ordering and lookup
// ---------------------------------------------------------------------------
describe('entries', () => {
  it('keeps the server order rather than ranking by severity', () => {
    const list = [entry({ factor: 'a', state: 'clear' }),
                  entry({ factor: 'b', state: 'flagged' })]
    expect(orderedEntries(list).map((e) => e.factor)).toEqual(['a', 'b'])
  })

  it('narrows to one state when asked', () => {
    const list = [entry({ factor: 'a', state: 'clear' }),
                  entry({ factor: 'b', state: 'flagged' })]
    expect(orderedEntries(list, 'flagged').map((e) => e.factor)).toEqual(['b'])
  })

  it('finds nothing without inventing an entry', () => {
    expect(findEntry([entry()], 'missing')).toBeNull()
    expect(findEntry(undefined, 'ndvi')).toBeNull()
    expect(findEntry([entry()], null)).toBeNull()
  })
})
