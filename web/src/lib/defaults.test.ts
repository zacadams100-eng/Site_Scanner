import { describe, expect, it } from 'vitest'
import { defaultFactors } from './defaults'

/**
 * A regression test for a defect only driving scanner #2 found.
 *
 * The opening factor list was hard-coded to land's factors, so the habitat
 * scanner — which exposes six, none of them `precip_total` — returned 422 on
 * every first load and the app showed an empty map with no stated reason.
 */
describe('opening factors follow the scanner', () => {
  it('keeps the preferred ones a scanner actually has', () => {
    const land = ['ndvi', 'lc_tree_pct', 'precip_total', 'lst_day', 'evi']
    expect(defaultFactors(land)).toEqual(
      ['ndvi', 'lc_tree_pct', 'precip_total', 'lst_day'])
  })

  it('never asks a scanner for a factor it does not expose', () => {
    const habitat = ['ndvi', 'ndmi', 'evi', 'lc_tree_pct', 'lc_dominant',
                     'water_occurrence']
    const picked = defaultFactors(habitat)
    for (const f of picked) expect(habitat).toContain(f)
    expect(picked).not.toContain('precip_total')
    expect(picked).not.toContain('lst_day')
  })

  it('tops up from the catalogue rather than opening with almost nothing', () => {
    const habitat = ['ndvi', 'ndmi', 'evi', 'lc_tree_pct', 'lc_dominant']
    expect(defaultFactors(habitat)).toHaveLength(4)
  })

  it('survives a scanner with fewer factors than the opening count', () => {
    expect(defaultFactors(['ndvi'])).toEqual(['ndvi'])
    expect(defaultFactors([])).toEqual([])
  })
})
