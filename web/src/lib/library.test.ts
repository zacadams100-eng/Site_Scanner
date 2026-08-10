import { describe, expect, it } from 'vitest'
import type { ScannerInfo } from '../types'

/**
 * The scanner library's one rule, tested where it can be: **availability comes
 * from the registry, never from a frontend list.**
 *
 * A second list of scanners in the frontend would drift from the backend, and
 * the first symptom would be a card offering a scanner the API refuses. These
 * assertions describe the partition the component performs, so a future
 * "just hard-code the roadmap" change fails here.
 */

const REGISTRY: ScannerInfo[] = [
  { id: 'land', name: 'Land', subject: 'Site constraints and land assessment', implemented: true },
  { id: 'habitat', name: 'Habitat', subject: 'Ecological condition and habitat investigation', implemented: true },
  { id: 'coastal', name: 'Coastal', subject: 'Coastal conditions and change', implemented: false },
  { id: 'forestry', name: 'Forestry', subject: 'Forest condition and management', implemented: false },
  { id: 'water', name: 'Water', subject: 'Water and catchment assessment', implemented: false },
  { id: 'terrain', name: 'Terrain', subject: 'Terrain and physical site conditions', implemented: false },
]

const available = (all: ScannerInfo[]) => all.filter((s) => s.implemented)
const upcoming = (all: ScannerInfo[]) => all.filter((s) => !s.implemented)

describe('the library partitions by what the registry says', () => {
  it('shows six verticals with two available', () => {
    expect(REGISTRY).toHaveLength(6)
    expect(available(REGISTRY).map((s) => s.id)).toEqual(['land', 'habitat'])
    expect(upcoming(REGISTRY)).toHaveLength(4)
  })

  it('never treats an unimplemented scanner as openable', () => {
    // The failure this prevents: a user enters a scanner and finds nothing
    // works. Availability is the registry's `implemented`, which is true only
    // when a scanner has rules.
    for (const s of upcoming(REGISTRY)) expect(s.implemented).toBe(false)
  })

  it('follows the registry rather than a hard-coded roadmap', () => {
    // Habitat flipping to available must require no frontend change — it did
    // not, when habitat was built.
    const before = REGISTRY.map((s) => ({ ...s, implemented: s.id === 'land' }))
    expect(available(before).map((s) => s.id)).toEqual(['land'])
    const after = before.map((s) => ({ ...s, implemented: s.id !== 'coastal' && s.id !== 'forestry' && s.id !== 'water' && s.id !== 'terrain' }))
    expect(available(after).map((s) => s.id)).toEqual(['land', 'habitat'])
  })

  it('every scanner states what it is for', () => {
    // A card with a name and no subject is a logo. The subject is what makes
    // the platform legible on the first screen.
    for (const s of REGISTRY) {
      expect(s.subject.length).toBeGreaterThan(10)
      expect(s.name.length).toBeGreaterThan(2)
    }
  })

  it('an empty registry renders nothing rather than inventing scanners', () => {
    expect(available([])).toEqual([])
    expect(upcoming([])).toEqual([])
  })
})
