import { describe, it, expect } from 'vitest'
import { certaintyOf, certaintyNote, hatchTile, HATCH_LOW, HATCH_ABSENT } from './uncertainty'
import type { Point } from '../types'

const point = (value: number | string | null, valid_fraction: number): Point =>
  ({ t: '2024-07', value, valid_fraction, interpolated: false })

describe('certaintyOf', () => {
  it('calls a well-observed month ok', () => {
    expect(certaintyOf(point(0.62, 0.95))).toBe('ok')
  })

  it('calls a sparsely observed month low', () => {
    expect(certaintyOf(point(0.62, 0.12))).toBe('low')
  })

  it('calls a null value absent, however good the coverage claims to be', () => {
    // A null with a high valid_fraction is a contradiction in the data, and
    // "absent" is the safe reading of it: there is no number to qualify.
    expect(certaintyOf(point(null, 0.99))).toBe('absent')
  })

  it('treats a missing point as absent rather than throwing', () => {
    // Scrubbing past the end of a series must not take the map down.
    expect(certaintyOf(undefined)).toBe('absent')
    expect(certaintyOf(null)).toBe('absent')
  })

  it('treats a non-finite number as absent', () => {
    expect(certaintyOf(point(NaN, 0.9))).toBe('absent')
  })

  it('uses the same 0.4 cut as the attribute table', () => {
    // If these ever drift apart, the table and the map disagree about the same
    // number and the user has no way to tell which one is lying.
    expect(certaintyOf(point(1, 0.39))).toBe('low')
    expect(certaintyOf(point(1, 0.4))).toBe('ok')
  })

  it('classifies categorical values by coverage like any other', () => {
    expect(certaintyOf(point('Grassland', 0.9))).toBe('ok')
    expect(certaintyOf(point('Grassland', 0.1))).toBe('low')
  })
})

describe('certaintyNote', () => {
  it('says nothing when there is nothing to caveat', () => {
    expect(certaintyNote(point(0.62, 0.95))).toBeNull()
  })

  it('quotes the actual coverage rather than an adjective', () => {
    const note = certaintyNote(point(0.62, 0.12))
    expect(note).toContain('12%')
  })

  it('distinguishes not measured from measured as zero', () => {
    // This is the whole point of drawing the absent case at all.
    const note = certaintyNote(point(null, 0))
    expect(note).toContain('not measured as zero')
  })

  it('names the month when it is given one', () => {
    expect(certaintyNote(point(null, 0), 'Jan 2018')).toContain('Jan 2018')
  })
})

describe('hatchTile', () => {
  it('produces an RGBA buffer of the declared size', () => {
    const t = hatchTile({ size: 8 })
    expect(t.width).toBe(8)
    expect(t.height).toBe(8)
    expect(t.data.length).toBe(8 * 8 * 4)
  })

  it('leaves most of the tile transparent so the value shows through', () => {
    const t = hatchTile(HATCH_LOW)
    let opaque = 0
    for (let i = 3; i < t.data.length; i += 4) if (t.data[i] > 0) opaque++
    // 1 pixel in every 4 along the diagonal — a quarter of the tile.
    expect(opaque).toBe(16)
    expect(opaque / (t.width * t.height)).toBeLessThan(0.5)
  })

  it('draws the absent hatch denser than the low-confidence one', () => {
    const count = (o: Parameters<typeof hatchTile>[0]) => {
      const t = hatchTile(o)
      let n = 0
      for (let i = 3; i < t.data.length; i += 4) if (t.data[i] > 0) n++
      return n
    }
    expect(count(HATCH_ABSENT)).toBeGreaterThan(count(HATCH_LOW))
  })

  it('tiles seamlessly: the pattern wraps on both axes', () => {
    // A tile whose right edge does not continue into its own left edge shows a
    // visible grid across the whole overlay.
    const size = 8, spacing = 4
    const t = hatchTile({ size, spacing, thickness: 1 })
    const on = (x: number, y: number) => t.data[((y * size + x) * 4) + 3] > 0
    for (let y = 0; y < size; y++) {
      // The pixel that would follow x = size - 1 is x = 0 of the next tile,
      // one step further along the diagonal.
      expect(on(0, (y + size) % size)).toBe(((0 + y) % spacing) < 1)
    }
  })

  it('uses a neutral ink, never a ramp colour', () => {
    // Hatching in a value colour would read as a value.
    const t = hatchTile(HATCH_LOW)
    for (let i = 0; i < t.data.length; i += 4) {
      if (t.data[i + 3] === 0) continue
      expect(t.data[i]).toBe(t.data[i + 1])
      expect(t.data[i + 1]).toBe(t.data[i + 2])
    }
  })

  it('clamps a nonsense alpha instead of wrapping it', () => {
    const t = hatchTile({ alpha: 4 })
    for (let i = 3; i < t.data.length; i += 4) {
      expect(t.data[i]).toBeLessThanOrEqual(255)
    }
  })
})
