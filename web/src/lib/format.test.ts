import { describe, expect, it } from 'vitest'
import { formatArea, formatRadius } from './format'
import { readRedLineFile } from './readRedLine'

describe('formatRadius', () => {
  it('names the red line rather than printing zero', () => {
    expect(formatRadius(0)).toBe('red line')
    expect(formatRadius(250)).toBe('250 m')
    expect(formatRadius(10_000)).toBe('10 km')
  })
})

describe('formatArea', () => {
  it('uses square metres below a hectare', () => {
    expect(formatArea(0.5)).toBe('5,000 m²')
    expect(formatArea(6.3)).toBe('6.3 ha')
  })
})

const file = (name: string, text: string) => ({ name, text: async () => text }) as unknown as File

describe('readRedLineFile', () => {
  it('reads a GeoJSON feature and closes the ring', async () => {
    const g = await readRedLineFile(file('site.geojson', JSON.stringify({
      type: 'Feature', properties: {},
      geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1]]] },
    })))
    expect(g.coordinates[0]).toEqual([[0, 0], [1, 0], [1, 1], [0, 0]])
  })

  it('says plainly when a file is not GeoJSON', async () => {
    await expect(readRedLineFile(file('site.shp', 'binary'))).rejects.toThrow(/not GeoJSON or KML/)
  })
})
