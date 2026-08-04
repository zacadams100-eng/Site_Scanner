/**
 * Finding your site.
 *
 * Until now the only way to reach a field was to pan and zoom across England
 * from wherever the map happened to open. Every serious GIS tool has a
 * "go here" box, and without one the drawing tools are unreachable for anyone
 * who does not already know where they are on an unlabelled basemap.
 *
 * Lookups go to postcodes.io — free, keyless, CORS-enabled, and serving ONS
 * and Ordnance Survey open data under the Open Government Licence. That
 * licence has an attribution condition, which is why `PLACES_ATTRIBUTION`
 * exists and is shown wherever results are.
 *
 * Typed coordinates are handled locally and never leave the browser, so the
 * one input form that always works needs no network at all.
 */

export const PLACES_ATTRIBUTION =
  'Postcode and place lookups contain OS data © Crown copyright and database ' +
  'right 2024, and ONS data © Crown copyright and database right 2024, ' +
  'licensed under the Open Government Licence v3.0 (via postcodes.io).'

const API = 'https://api.postcodes.io'

export interface Place {
  id: string
  name: string
  /** The line under the name — county, district, or the coordinates. */
  detail: string
  lng: number
  lat: number
  kind: 'postcode' | 'place' | 'coords'
  /** How far in to fly. A postcode is a street; a town is a town. */
  zoom: number
}

export interface Bbox { west: number; south: number; east: number; north: number }

/** UK postcodes, whole or partial: "GU2", "GU2 7XH", "gu27xh". */
export function looksLikePostcode(q: string): boolean {
  return /^[a-z]{1,2}\d[a-z\d]?(\s*\d[a-z]{2})?$/i.test(q.trim())
}

/**
 * "51.235, -0.57" typed or pasted straight in.
 *
 * Order is lat, lng — the convention everywhere except GeoJSON, and the one a
 * user copying out of Google Maps will have. Where only one of the two numbers
 * can be a latitude the pair is swapped rather than refused, because a user
 * who pastes GeoJSON order means the same place and would otherwise be sent to
 * the middle of the sea with no explanation.
 */
export function parseCoordinates(q: string): Place | null {
  const m = q.trim().match(/^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/)
  if (!m) return null
  let lat = Number(m[1])
  let lng = Number(m[2])
  if (Math.abs(lat) > 90 && Math.abs(lng) <= 90) [lat, lng] = [lng, lat]
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null
  return {
    id: `coords:${lat},${lng}`,
    name: `${lat.toFixed(5)}, ${lng.toFixed(5)}`,
    detail: 'Coordinates',
    lng,
    lat,
    kind: 'coords',
    zoom: 15,
  }
}

export function withinCoverage(p: { lng: number; lat: number }, bbox: Bbox): boolean {
  return p.lng >= bbox.west && p.lng <= bbox.east && p.lat >= bbox.south && p.lat <= bbox.north
}

type Fetcher = typeof fetch

async function getJson(url: string, signal: AbortSignal | undefined, f: Fetcher): Promise<any> {
  const r = await f(url, { signal })
  // postcodes.io answers 404 with a JSON body for "no such postcode", which is
  // a legitimate empty result rather than a failure.
  if (!r.ok && r.status !== 404) throw new Error(`Lookup failed (${r.status})`)
  return r.json()
}

function fromPostcode(p: any): Place | null {
  if (typeof p?.longitude !== 'number' || typeof p?.latitude !== 'number') return null
  return {
    id: `pc:${p.postcode}`,
    name: p.postcode,
    detail: [p.admin_ward, p.admin_district].filter(Boolean).join(', ') || 'Postcode',
    lng: p.longitude,
    lat: p.latitude,
    kind: 'postcode',
    zoom: 15,
  }
}

function fromPlace(p: any): Place | null {
  if (typeof p?.longitude !== 'number' || typeof p?.latitude !== 'number') return null
  return {
    id: `pl:${p.code ?? p.name_1}`,
    name: p.name_1 ?? 'Unnamed place',
    detail: [p.county_unitary, p.region].filter(Boolean).join(', ') || 'Place',
    lng: p.longitude,
    lat: p.latitude,
    kind: 'place',
    // A named place is an area, not a point — landing at street level inside
    // one tells the user nothing about where they are.
    zoom: 12,
  }
}

/**
 * Postcodes and place names, merged into one ranked list.
 *
 * Both lookups are issued together and a failure in one does not sink the
 * other: a place-name search that works while the postcode endpoint is having
 * a bad day is still a working search box.
 */
export async function searchPlaces(
  query: string,
  signal?: AbortSignal,
  f: Fetcher = fetch,
): Promise<Place[]> {
  const q = query.trim()
  if (q.length < 2) return []

  const coords = parseCoordinates(q)
  if (coords) return [coords]

  const url = encodeURIComponent(q)
  const wanted: Promise<Place[]>[] = [
    getJson(`${API}/places?q=${url}&limit=6`, signal, f)
      .then((j) => (j?.result ?? []).map(fromPlace).filter(Boolean) as Place[]),
  ]
  if (looksLikePostcode(q)) {
    wanted.push(
      getJson(`${API}/postcodes?q=${url}&limit=6`, signal, f)
        .then((j) => (j?.result ?? []).map(fromPostcode).filter(Boolean) as Place[]),
    )
  }

  const settled = await Promise.allSettled(wanted)
  const ok = settled.filter((s) => s.status === 'fulfilled')
  if (!ok.length) {
    throw new Error('Could not reach the place lookup. Check your connection, ' +
                    'or type coordinates as "51.235, -0.57".')
  }

  const out: Place[] = []
  const seen = new Set<string>()
  // Postcodes first when the query looks like one — someone typing "GU2" wants
  // the postcode, not a village that happens to match the letters.
  for (const s of ok.map((s) => (s as PromiseFulfilledResult<Place[]>).value).reverse()) {
    for (const p of s) {
      if (seen.has(p.id)) continue
      seen.add(p.id)
      out.push(p)
    }
  }
  return out.slice(0, 8)
}
