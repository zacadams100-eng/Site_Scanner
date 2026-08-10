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

/** One thing the server noticed in the series. See insights.py — every field
 *  is arithmetic over observations already on screen, never a prediction. */
export interface Insight {
  factor: string
  kind: 'trend' | 'anomaly' | 'step' | 'static' | 'coverage'
  /** The finding as a sentence. Carries its own "demo data" caveat when it
   *  came from generated numbers — deliberately in the text rather than in a
   *  sibling field, so no layout can drop it. */
  text: string
  /** 0–1. Used for ranking only; not a probability. */
  notability: number
  source?: 'earth-engine' | 'open-data' | 'generated'
  r2?: number
  t?: number | null
  n?: number
  z?: number
  effect_size?: number
  missing?: number
  total?: number
  at?: string
  period?: string
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
  source?: 'earth-engine' | 'open-data' | 'generated'
  /** Which service answered, and whether anyone has run it for real. Present
   *  on real columns only; mirrors the catalogue's per-factor provenance. */
  provenance?: Provenance | null
  /** Round-trip cost of the real path, so the price of live queries is visible
   *  rather than guessed at. */
  elapsed_ms?: number
  /** True when the server answered from its series cache rather than querying
   *  Earth Engine again. */
  cached?: boolean
  /** How this site's latest reading compares with England.
   *
   *  Present only on a real column with a sampled baseline behind it — a
   *  generated value is never ranked, because a percentile with a sourced
   *  denominator and an invented numerator is the most convincing wrong
   *  number this app could show. Absent is the common case; treat it as
   *  "no yardstick", never as "average". */
  baseline?: Baseline | null
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
  /** What the server noticed, most notable first. Absent on an older backend,
   *  which is why the panel treats undefined as "nothing to show". */
  insights?: Insight[]
  counts?: {
    total: number
    shown: number
    from_real_data: number
    from_generated_data: number
  }
  /** What deserves investigation. Absent on an older backend. See radar.py. */
  radar?: Radar
}

/** Where a flag's numbers came from, and how well that has been proven.
 *  `written` means implemented against the documented API and never yet run
 *  against the live service — not the same claim as `verified`. */
export interface FlagProvenance {
  factor: string
  name: string
  source?: 'earth-engine' | 'open-data' | 'generated'
  publisher?: string
  endpoint?: string
  status: 'verified' | 'written' | 'unknown'
}

export interface Flag {
  id: string
  topic: string
  topic_name: string
  severity: 'high' | 'medium' | 'low'
  text: string
  /** The observed value and the threshold it crossed, so a flag is checkable
   *  rather than merely assertive. */
  evidence: Record<string, string | number>
  factors: string[]
  provenance: FlagProvenance[]
  investigations: string[]
}

/**
 * Three states, never two.
 *
 * `clear` means it was checked and nothing crossed a threshold; `not_assessed`
 * means it was not checked. Collapsing those two into one silence is what
 * turns this feature from a help into a hazard, so the type will not let a
 * component treat "absent" as "fine".
 */
export interface RadarTopic {
  id: string
  name: string
  state: 'flagged' | 'clear' | 'not_assessed'
  flags: number
  checked: string[]
}

export interface Unassessed {
  rule: string
  topic: string
  topic_name: string
  asks: string
  /** `not_selected` is one click to fix; `demo_data` is a wall. */
  reason: 'not_selected' | 'demo_data'
  factors: string[]
  /** Display names for `factors`. "Add flood_zone2_pct" is a column, not a
   *  sentence. Optional so an older backend still renders. */
  factor_names?: string[]
  text: string
}

export interface Investigation {
  id: string
  name: string
  blurb: string
  priority: 'high' | 'medium' | 'low'
  /** Flag ids. Never empty — no recommendation exists without a flag. */
  why: string[]
  why_text: string[]
}

export interface Radar {
  flags: Flag[]
  topics: RadarTopic[]
  investigations: Investigation[]
  not_assessed: Unassessed[]
  counts: {
    flags: number
    high: number
    topics_flagged: number
    topics_clear: number
    topics_not_assessed: number
  }
  limits: string
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

/**
 * A natural-language answer.
 *
 * `answered_from: 'series'` is the contract that matters: every figure in
 * `answer` was computed from `series`, not written by a model. A model may
 * have rephrased the sentence — `phrased_by` says so — but it is never given
 * the question without the computed answer, so it cannot introduce a number.
 */
export interface AskFinding {
  factor_id: string
  label: string
  unit: string
  source: string
  observed: boolean
  verdict: 'trend' | 'flat' | 'level' | 'extreme' | 'no-data'
  text: string
  from?: number
  to?: number
  from_value?: number
  to_value?: number
  change?: number
  change_pct?: number | null
}

export interface AskResponse {
  question: string
  understood: {
    factor_ids: string[]
    scores: Record<string, number>
    from_year: number
    to_year: number
    intent: string
  }
  findings: AskFinding[]
  answer: string
  answered_from: 'series'
  phrased_by?: 'claude'
  suggestions?: string[]
  series?: Record<string, Series>
  area_ha?: number
}

/**
 * A site's reading placed against a sample of England.
 *
 * `phrase` is the sentence to show; `percentile` is there for anyone who wants
 * the number. `n` and `built` travel with both because a percentile from 60
 * points and one from 6,000 are different claims.
 */
export interface Baseline {
  percentile: number
  median: number | null
  p10: number | null
  p90: number | null
  n: number
  built: string | null
  basis: string
  phrase: string
}
