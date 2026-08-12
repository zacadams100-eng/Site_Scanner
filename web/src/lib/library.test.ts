import { describe, expect, it } from 'vitest'
import type { Catalog, ScannerInfo } from '../types'
import {
  STATUS_NOTE, builtDomains, domainGaps, isOpenable, sections, statusOf, tally,
} from './library'

/**
 * The scanner library's rules.
 *
 * The original version of this file tested a partition written inline in the
 * component, against a hand-written registry fixture. It is now testing the
 * real module, and it keeps every guarantee it had — availability comes from
 * the registry, nothing is openable that the API refuses, every scanner states
 * its subject — plus the ones the taxonomy added.
 *
 * The new guarantee that matters most is about **partial** scanners. Before,
 * a scanner was available or it was not. Now three of the four built ones
 * cover part of their subject, and a library that showed them as simply
 * "available" would set up the exact misreading this product exists to
 * prevent: a clear result from Water taken as "no water issues", when
 * groundwater was never asked.
 */

const SCANNERS: ScannerInfo[] = [
  {
    id: 'land', name: 'Land', subject: 'Site constraints and land assessment',
    implemented: true, family: 'foundation', status: 'live',
    topic_count: 7, factor_count: 271, rule_count: 25,
    domains: [
      { id: 'ground', name: 'Ground', subject: 'What it is made of', implemented: true, blocked_by: '' },
      { id: 'terrain', name: 'Terrain', subject: 'Shape of the ground', implemented: true, blocked_by: '' },
    ],
  },
  {
    id: 'water', name: 'Water', subject: 'Water, flood and coastal assessment',
    implemented: true, family: 'foundation', status: 'partial',
    topic_count: 6, factor_count: 9, rule_count: 11,
    domains: [
      { id: 'flood', name: 'Flood', subject: 'Designated flood risk', implemented: true, blocked_by: '' },
      { id: 'coastal', name: 'Coastal', subject: 'Low-lying exposure', implemented: true, blocked_by: '' },
      {
        id: 'groundwater', name: 'Groundwater', subject: 'Aquifers and water table',
        implemented: false,
        blocked_by: 'No groundwater source is integrated. The Environment Agency publishes aquifer designations; none is ingested.',
      },
    ],
  },
  {
    id: 'ecology', name: 'Ecology', subject: 'Ecological condition and habitat evidence',
    implemented: true, family: 'foundation', status: 'partial',
    topic_count: 7, factor_count: 10, rule_count: 16, domains: [],
  },
  {
    id: 'planning', name: 'Planning', subject: 'Planning designations and constraint',
    implemented: true, family: 'development', status: 'partial',
    topic_count: 1, factor_count: 7, rule_count: 7, domains: [],
  },
  {
    id: 'infrastructure', name: 'Infrastructure', subject: 'Utilities, transport and network capacity',
    implemented: false, family: 'development', status: 'planned',
    topic_count: 0, factor_count: 0, rule_count: 0, domains: [],
  },
  {
    id: 'heritage', name: 'Heritage', subject: 'Designated heritage assets and archaeology',
    implemented: false, family: 'culture', status: 'planned',
    topic_count: 0, factor_count: 0, rule_count: 0, domains: [],
  },
]

const CATALOG = {
  scanners: SCANNERS,
  families: [
    { id: 'foundation', name: 'Foundation', subject: 'The physical ground truth', scanners: ['land', 'water', 'ecology'] },
    { id: 'development', name: 'Development', subject: 'What may be built here', scanners: ['planning', 'infrastructure'] },
    { id: 'culture', name: 'Culture', subject: 'What a place has been', scanners: ['heritage'] },
  ],
} as unknown as Catalog

describe('the library follows the registry and never a frontend list', () => {
  it('groups into the families the backend sent, in that order', () => {
    // Not grouped here. The backend decided both the grouping and the order,
    // and re-deriving either would be a second opinion that drifts.
    expect(sections(CATALOG).map((s) => s.family.id))
      .toEqual(['foundation', 'development', 'culture'])
  })

  it('never treats an unbuilt scanner as openable', () => {
    // The failure this prevents: a user enters a scanner and finds nothing
    // works, because the API refuses it.
    for (const s of SCANNERS) {
      expect(isOpenable(s)).toBe(s.implemented)
    }
  })

  it('follows the registry rather than a hard-coded roadmap', () => {
    // Planning flipping to built must require no frontend change — it did
    // not, when the taxonomy landed.
    const before = SCANNERS.map((s) =>
      s.id === 'planning' ? { ...s, implemented: false, status: 'planned' as const } : s)
    expect(before.filter(isOpenable).map((s) => s.id))
      .toEqual(['land', 'water', 'ecology'])
    expect(SCANNERS.filter(isOpenable).map((s) => s.id))
      .toEqual(['land', 'water', 'ecology', 'planning'])
  })

  it('every scanner states what it is for', () => {
    // A card with a name and no subject is a logo. The subject is what makes
    // the platform legible on the first screen.
    for (const s of SCANNERS) {
      expect(s.subject.length).toBeGreaterThan(10)
      expect(s.name.length).toBeGreaterThan(2)
    }
  })

  it('an empty registry renders nothing rather than inventing scanners', () => {
    expect(sections(null)).toEqual([])
    expect(sections({ scanners: [] } as unknown as Catalog)).toEqual([])
  })

  it('drops a family with no scanners rather than rendering an empty heading', () => {
    const withEmpty = {
      ...CATALOG,
      families: [...(CATALOG.families ?? []),
        { id: 'economics', name: 'Economics', subject: '', scanners: [] }],
    } as Catalog
    expect(sections(withEmpty).map((s) => s.family.id)).not.toContain('economics')
  })

  it('falls back to one ungrouped section when the backend sends no families', () => {
    // A deployment mid-upgrade. The library still works and claims nothing
    // about a structure it was not told about.
    const old = { scanners: SCANNERS } as unknown as Catalog
    const out = sections(old)
    expect(out).toHaveLength(1)
    expect(out[0].scanners).toHaveLength(SCANNERS.length)
  })

  it('ignores a family naming a scanner the registry does not have', () => {
    const stale = {
      ...CATALOG,
      families: [{ id: 'foundation', name: 'Foundation', subject: '', scanners: ['land', 'ghost'] }],
    } as Catalog
    expect(sections(stale)[0].scanners.map((s) => s.id)).toEqual(['land'])
  })
})

describe('what works comes first', () => {
  it('sorts built scanners above unbuilt ones inside a family', () => {
    const development = sections(CATALOG).find((s) => s.family.id === 'development')!
    expect(development.scanners.map((s) => s.id)).toEqual(['planning', 'infrastructure'])
  })

  it('marks a section with nothing openable in it', () => {
    const culture = sections(CATALOG).find((s) => s.family.id === 'culture')!
    expect(culture.openable).toBe(false)
    const foundation = sections(CATALOG).find((s) => s.family.id === 'foundation')!
    expect(foundation.openable).toBe(true)
  })
})

describe('a partial scanner says which half it is', () => {
  it('does not present partial coverage as complete', () => {
    const water = SCANNERS.find((s) => s.id === 'water')!
    expect(statusOf(water)).toBe('partial')
    expect(statusOf(SCANNERS.find((s) => s.id === 'land')!)).toBe('live')
  })

  it('names the domains that were never asked', () => {
    // The whole point. A clear result from Water covers flood and coastal;
    // groundwater was not assessed, and the library says so before the user
    // picks the scanner rather than after.
    const water = SCANNERS.find((s) => s.id === 'water')!
    expect(builtDomains(water).map((d) => d.id)).toEqual(['flood', 'coastal'])
    expect(domainGaps(water).map((d) => d.id)).toEqual(['groundwater'])
  })

  it('every named gap says what is actually missing', () => {
    // "Coming soon" is not something a professional can plan around.
    for (const s of SCANNERS) {
      for (const d of domainGaps(s)) {
        expect(d.blocked_by.length).toBeGreaterThan(40)
      }
    }
  })

  it('warns that a clear result covers only what was assessed', () => {
    // The sentence that stops a clear result being read as a clean site.
    expect(STATUS_NOTE.partial).toMatch(/never asked/i)
  })

  it('reads an undescribed scanner as partial rather than complete', () => {
    // The cautious fallback. Claiming complete coverage on a scanner that
    // never said so is the error that misleads; the reverse only understates.
    const undescribed = { id: 'x', name: 'X', subject: 'Something', implemented: true } as ScannerInfo
    expect(statusOf(undescribed)).toBe('partial')
    expect(statusOf({ ...undescribed, implemented: false })).toBe('planned')
  })
})

describe('the tally counts the registry and cannot exceed it', () => {
  it('counts by status', () => {
    expect(tally(CATALOG)).toEqual({
      scanners: 6, live: 1, partial: 3, planned: 2, families: 3, openable: 4,
    })
  })

  it('is all zeroes for an empty registry', () => {
    expect(tally(null).scanners).toBe(0)
    expect(tally(null).openable).toBe(0)
  })
})
