// Shapes returned by the backend. These mirror catalog.py and
// routes_catalog.py exactly — if one moves, the other must.

export type Kind = 'continuous' | 'categorical'
export type Cadence = 'monthly' | 'annual' | 'static' | '5 years' | 'periodic'

export interface Base {
  id: string
  name: string
  source: string
  licence: string
  /** The exact notice this licence requires — not the licence name. Most of
   *  these permit commercial use only on condition this text is displayed, so
   *  it travels with the numbers into the UI and into every export. */
  attribution: string
  /** Triage flag from the catalogue: 'yes' or 'verify'. Not legal advice. */
  commercial?: string
  url: string
  native_cadence: string
  cadence: string
  resolution_m: number | null
  stored: boolean
}

export interface Factor {
  id: string
  name: string
  base: string
  group: string
  unit: string
  kind: Kind
  cadence: Cadence
  lo: number | null
  hi: number | null
  derived: boolean
  note: string
  /** True where this factor returns real observations — satellite, or public
   *  open data. Absent on an older backend, which is why the UI treats
   *  undefined as "not live" rather than as unknown. */
  real?: boolean
  /** Present only when `real`. Who publishes the data, which host actually
   *  answers for it, and whether anyone has run that host for real. */
  provenance?: Provenance
}

export interface Provenance {
  /** The organisation that publishes the data — Natural England, HM Land
   *  Registry, ESA. */
  source: string
  /** The host we actually query, which is rarely the publisher: Natural
   *  England's designations reach us through planning.data.gov.uk and ESA's
   *  imagery through Earth Engine. A user shown only the publisher cannot
   *  reproduce the number. */
  endpoint: string
  /** `verified` — run against the live service and checked by a human.
   *  `written` — implemented against the documented API and covered by tests
   *  using recorded fixtures, but never yet run for real. The distinction is
   *  shown, because "we wrote it" must not read as "we ran it". */
  status: 'verified' | 'written'
  /** What this source cannot tell you. Worth reading before quoting it. */
  note?: string
}

export interface Catalog {
  factors: Factor[]
  bases: Base[]
  groups: string[]
  real_factor_ids?: string[]
  verified_factor_ids?: string[]
  class_values: Record<string, string[]>
  summary: {
    factor_count: number
    base_count: number
    stored_base_count: number
    monthly_base_count: number
    derived_factor_count: number
    group_count: number
    real_factor_count?: number
    verified_factor_count?: number
    generated_factor_count?: number
    /** real_factor_count / factor_count, 0..1. */
    real_share?: number
  }
  coverage: { name: string; bbox: { west: number; south: number; east: number; north: number } }
  time: { start: string; end: string; steps: string[] }
}

/** A single observation. `value: null` is a real gap — never interpolate it. */
export interface Point {
  t: string
  value: number | string | null
  valid_fraction: number
  interpolated: boolean
}

/** One row per year — the attribute table's default view. */
export interface AnnualRow {
  year: number
  value: number | string | null
  min: number | null
  max: number | null
  months_observed: number
  months_total: number
  confidence: number
}

export interface Series {
  factor_id: string
  /** Where this column's numbers came from. A half-real catalogue is fine —
   *  pretending it is uniformly one or the other is not. */
  source?: 'earth-engine' | 'generated'
  /** Round-trip cost of the real path, so the price of live queries is visible
   *  rather than guessed at. */
  elapsed_ms?: number
  /** True when the server answered from its series cache rather than querying
   *  Earth Engine again. */
  cached?: boolean
  /** Set when the real path failed and the generator stood in. */
  error?: string
  kind: Kind
  cadence: Cadence
  unit: string
  points: Point[]
  annual: AnnualRow[]
  meta: Factor & { base_meta: Base }
}

export interface SeriesResponse {
  area_ha: number
  centroid: { lng: number; lat: number }
  precision: 'approx' | 'exact'
  real_factors?: string[]
  steps: string[]
  series: Record<string, Series>
}

export interface Cell {
  id: string
  bbox: [number, number, number, number]
  offset: number
}

export interface CellsResponse {
  cells: Cell[]
  area_ha: number
  centroid: { lng: number; lat: number }
}

export type DrawMode = 'rect' | 'circle' | 'freehand' | 'point' | null

/**
 * A place the user has marked and named — an access point, a substation, a
 * pinch point, the spot the photograph was taken from.
 *
 * Deliberately separate from the area: the AOI is what gets measured, and a
 * marker is a note about where something is. Conflating them would mean every
 * pin triggered a query.
 */
export interface Marker {
  id: string
  name: string
  lng: number
  lat: number
}
