/** Reads a dropped or picked file and returns the first polygon in it.
 *  Most serious users already have their boundary in a file; making them
 *  re-trace it is exactly the friction this product exists to remove. */
export async function readRedLineFile(file: File): Promise<GeoJSON.Polygon> {
  const text = await file.text()
  const name = file.name.toLowerCase()

  if (name.endsWith('.kml') || text.trimStart().startsWith('<')) {
    const doc = new DOMParser().parseFromString(text, 'text/xml')
    const coords = doc.querySelector('Polygon coordinates')?.textContent
    if (!coords) throw new Error('No polygon found in that KML file.')
    const ring = coords.trim().split(/\s+/).map((tuple) => {
      const [lng, lat] = tuple.split(',').map(Number)
      return [lng, lat]
    })
    if (ring.length < 3) throw new Error('That KML polygon has too few points.')
    return { type: 'Polygon', coordinates: [closeRing(ring)] }
  }

  let json: any
  try {
    json = JSON.parse(text)
  } catch {
    throw new Error('That file is not GeoJSON or KML. Shapefiles must be ' +
                    'converted first — QGIS exports GeoJSON directly.')
  }

  const geom = findPolygon(json)
  if (!geom) throw new Error('No polygon found in that file.')
  return geom
}

function findPolygon(node: any): GeoJSON.Polygon | null {
  if (!node || typeof node !== 'object') return null
  if (node.type === 'Polygon' && Array.isArray(node.coordinates)) {
    return { type: 'Polygon', coordinates: [closeRing(node.coordinates[0])] }
  }
  if (node.type === 'MultiPolygon' && node.coordinates?.[0]) {
    // Take the largest ring rather than the first — a MultiPolygon of an
    // estate usually leads with an outbuilding.
    const biggest = node.coordinates.reduce((a: any, b: any) =>
      (b[0]?.length ?? 0) > (a[0]?.length ?? 0) ? b : a)
    return { type: 'Polygon', coordinates: [closeRing(biggest[0])] }
  }
  if (node.type === 'Feature') return findPolygon(node.geometry)
  if (node.type === 'FeatureCollection') {
    for (const f of node.features ?? []) {
      const g = findPolygon(f)
      if (g) return g
    }
  }
  if (node.geometry) return findPolygon(node.geometry)
  return null
}

function closeRing(ring: number[][]): number[][] {
  if (!ring?.length) return ring
  const [a, b] = [ring[0], ring[ring.length - 1]]
  return a[0] === b[0] && a[1] === b[1] ? ring : [...ring, ring[0]]
}
