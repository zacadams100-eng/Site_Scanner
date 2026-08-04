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
}

export interface Catalog {
  factors: Factor[]
  bases: Base[]
  groups: string[]
  class_values: Record<string, string[]>
  summary: {
    factor_count: number
    base_count: number
    stored_base_count: number
    monthly_base_count: number
    derived_factor_count: number
    group_count: number
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

export type DrawMode = 'rect' | 'circle' | 'freehand' | null
