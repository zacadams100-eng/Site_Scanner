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
  /** Temporal metrics paired with the finding the engine reached for each. */
  historical?: HistoricalEntry[]
  /** Per-factor traceability. Contextual to this report — the factors the
   *  rules wanted, never the whole catalogue. See evidence.py. */
  evidence?: EvidenceEntry[]
  /** The investigation workspace: each investigation joined to what raised it
   *  and the evidence pack behind it. See investigation.py — deliberately
   *  unable to tell which domain it is assembling for. */
  workspace?: InvestigationWorkspaceEntry[]
  methodology?: Methodology
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
  /** `partial` — some of this topic's checks ran and others could not. A topic
   *  with two checks where only one ran is not a clear topic. */
  state: 'flagged' | 'clear' | 'partial' | 'not_assessed'
  flags: number
  checked: string[]
  /** "2 of 3 indicators assessed". What makes `flagged` and `clear` mean
   *  something — without it both are bare adjectives. */
  coverage: { assessed: number; total: number }
  checks: { rule: string; asks: string; indicators: string[]
            assessed: boolean; reason?: string | null }[]
  /** One sentence naming what was read and what was not. */
  detail: string
  informational: number
}

export interface Unassessed {
  rule: string
  topic: string
  topic_name: string
  asks: string
  /** `not_selected` is one click to fix; `demo_data` is a wall. */
  /** `no_data` — a real source was asked and returned nothing usable.
   *  Distinct from both: the service answered, with silence. */
  reason: 'not_selected' | 'demo_data' | 'no_data'
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
  /** What to actually do. A recommendation that stops at naming a survey
   *  leaves the reader to work out who to ring. */
  next_step?: string
  evidence_factors?: string[]
}

/** A measured fact that is neither good nor bad. Bound by the same real-data
 *  rule as a flag: a generated informational finding is still a fabricated
 *  fact about a real place. */
export interface InfoFinding {
  id: string
  topic: string
  topic_name: string
  text: string
  evidence: Record<string, string | number>
  factors: string[]
  provenance: FlagProvenance[]
}

/** One row of the audit trail: a factor a rule wanted, and what became of it. */
export interface LogRow {
  factor: string
  name: string
  state: 'assessed' | 'not_selected' | 'generated'
  publisher?: string | null
  endpoint?: string | null
  status?: 'verified' | 'written' | null
  source?: string | null
  at: string
}

/**
 * How much of this site we were able to look at.
 *
 * Deliberately **not** a score, and `note` says so. A site at 90% is not
 * better than one at 50% — we simply know more about it. Collapsing this into
 * "Site health: 72/100" is the most commercially attractive wrong turn
 * available to this product, because a score hides its own inputs and the
 * entire argument for this tool is that it shows them.
 */
export interface Coverage {
  relevant: number
  assessed: number
  /** 0–1. */
  share: number
  flagged: number
  clear: number
  informational: number
  not_assessed: number
  /** Split by cause: one is a click, the other is a wall. */
  not_selected: number
  generated: number
  verified: number
  note: string
}

export interface Radar {
  flags: Flag[]
  informational: InfoFinding[]
  topics: RadarTopic[]
  investigations: Investigation[]
  not_assessed: Unassessed[]
  log: LogRow[]
  assessed_at: string
  coverage: Coverage
  counts: {
    flags: number
    high: number
    informational: number
    topics_flagged: number
    topics_clear: number
    topics_partial: number
    topics_not_assessed: number
  }
  /** "A clear result means we checked. An empty result means we could not." */
  principle: string
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


// --- Evidence comparison ----------------------------------------------------
// See COMPARISON_CONTRACT.md. The product answers "how do the evidence
// profiles differ", never "which site wins" — so there is no rank, no score
// and no ordering field anywhere in these types, and adding one would be an
// EM10 violation rather than a feature.

export interface CompareSiteSummary {
  id: string
  name: string
  flags: number
  high: number
  informational: number
  /** A real source returned a usable value. Not "we looked at it". */
  observed: number
  relevant: number
  not_assessed: number
  /** 0–1. Coverage, never quality. */
  share: number
  coverage_note: string
  area_ha?: number
}

export interface CompareTopicCell {
  id: string
  state: 'flagged' | 'clear' | 'partial' | 'not_assessed'
  coverage: { assessed: number; total: number }
  flags: number
  detail: string
}

export interface CompareTopic {
  id: string
  name: string
  sites: CompareTopicCell[]
  /** False where the sites were not assessed to the same depth. Their results
   *  then describe different amounts of evidence rather than different ground. */
  comparable: boolean
  /** The sites differ from each other in how much was assessed. Narrower than
   *  `!comparable`: three sites all at 0/2 are not unevenly evidenced, they
   *  are uniformly unevidenced. */
  uneven: boolean
  assessed_for_none: boolean
  note: string
}

export interface CompareDifference {
  kind: 'value' | 'coverage' | 'flags'
  factor?: string
  text: string
  sites: string[]
}

export interface Comparison {
  sites: CompareSiteSummary[]
  topics: CompareTopic[]
  differences: CompareDifference[]
  /** Fires unprompted when the sites were not examined to comparable depth.
   *  Fewer flags can mean less looked at. */
  coverage_warning: string
  principle: string
  limits: string
}

// --- Historical evidence ----------------------------------------------------
// See HISTORICAL_EVIDENCE_MODEL.md. A metric says what happened; the finding
// beside it was decided by the engine. The UI renders both and derives neither
// — EVIDENCE_MODEL.md EM11.

export interface HistoricalMetric {
  baseline: number | null
  recent: number | null
  change: number | null
  /** Null where the baseline was zero and a percentage would be undefined. */
  change_pct: number | null
  change_type: 'relative' | 'absolute' | null
  baseline_years: number[]
  recent_years: number[]
  years_usable: number
  years_total: number
  year_coverage: number
  observation_coverage: number
  /** Whether a rule was permitted to evaluate this. A statement about the
   *  evidence, not about the site. */
  meets_minimum_evidence: boolean
  /** Plain words naming what was missing, when something was. */
  shortfall: string
  method_version: string
  source?: string
  real: boolean
  season: number[]
}

export interface HistoricalFinding {
  state: 'flagged' | 'clear' | 'informational' | 'not_assessed'
  reason: string | null
  text?: string
  flag?: Flag | null
}

export interface HistoricalEntry {
  id: string
  name: string
  factor: string
  rule: string
  /** The threshold, what kind of threshold it is, and what it is for. Part of
   *  the evidence, not a tooltip: Contour does not present its own reporting
   *  threshold as an external fact. */
  rule_meta: Record<string, string | number>
  available: boolean
  metric: HistoricalMetric | null
  finding: HistoricalFinding | null
}

export interface Methodology {
  version: string
  seasons: Record<string, number[]>
  min_observations_per_year: number
  period_years: number
  min_year_coverage: number
  rules: string[]
}


/**
 * One factor's evidence, as the explorer renders it.
 *
 * `claims` is the reason this exists. Everything above it is provenance the
 * radar already had; the pair of sentences is what stops a reader completing
 * `measurement → diagnosis` when Contour only supports
 * `measurement → investigation`.
 */
export interface EvidenceFinding {
  id: string
  kind: 'flag' | 'info'
  text: string
  severity: 'high' | 'medium' | 'low' | null
  threshold: string
  evidence: Record<string, string | number>
  /** The rule's own account of its threshold. Empty for an informational
   *  finding, which applies none — and must not appear to. */
  rule_meta: Record<string, string | number>
}

export interface EvidenceSource {
  /** Whose data it is. */
  publisher: string
  /** Which service actually answered — Sentinel-2 reaches this product
   *  *through* Earth Engine, and a user told only "Copernicus" would look for
   *  the number in the wrong place (HE1). */
  endpoint: string
  dataset: string
  /** A fact about the data. */
  licence: string
  attribution: string
  /** This project's own unverified reading of that licence. Not the same
   *  thing, and never merged with it. */
  clearance: string
  /** What this deployment can actually prove, now (EM5). */
  runtime: string
  kind: string
}

export interface EvidenceEntry {
  factor: string
  name: string
  state: 'flagged' | 'clear' | 'informational' | 'not_assessed'
  reason: 'not_selected' | 'demo_data' | 'no_data' | null
  severity: 'high' | 'medium' | 'low' | null
  findings: EvidenceFinding[]
  source: EvidenceSource
  investigations: { id: string; name: string; priority: string; why: string[] }[]
  assessed_at: string
  /** Lists, not paragraphs: three findings joined into one block is a wall
   *  of prose in the place a reader is trying to read carefully. */
  claims: { established: string[]; not_established: string[] }
}


/**
 * The Site Investigation Brief — the artefact that leaves the product.
 *
 * Not a prettier report. A different document, answering: here is the evidence
 * we established about this site, and the professional questions that remain.
 * Every field is a projection of a payload that already satisfies EM1–EM11;
 * nothing here is computed in the browser.
 */
export interface BriefFinding {
  factor: string
  name: string
  severity: 'high' | 'medium' | 'low' | null
  findings: { text: string; threshold: string; rule: string; method: string }[]
  established: string[]
  /** Never empty. The candidate EM12, enforced on this surface first. */
  not_established: string[]
  investigations: string[]
  source: EvidenceSource
}

export interface BriefGap {
  reason: string
  /** The cause in words. A code in a document is a code to its reader. */
  label: string
  count: number
  factors: string[]
}

export interface Brief {
  sections: string[]
  site: {
    name: string
    area_ha: number | null
    centroid: { lng: number; lat: number }
    assessed_at: string
  }
  coverage: {
    assessed: number
    relevant: number
    not_assessed: number
    flagged: number
    clear: number
    informational: number
    not_loaded: number
    no_live_source: number
    note: string
  }
  findings: BriefFinding[]
  informational: { factor: string; name: string; text: string; not_established: string[] }[]
  historical: {
    name: string
    state: string
    change_pct: number | null
    baseline: number | null
    recent: number | null
    baseline_years: number[]
    recent_years: number[]
    years_usable: number | null
    years_total: number | null
    method: string
  }[]
  gaps: BriefGap[]
  log: {
    factor: string; name: string; source: string; endpoint: string
    status: string; verified: boolean; at: string
  }[]
  methodology: {
    historical: Record<string, unknown>
    attributions: string[]
    limits: string
  }
  principle: string
}


/**
 * One investigation, assembled.
 *
 * Every domain-specific word here arrives as data — the investigation's name
 * and next step from `radar.INVESTIGATIONS`, the rule's name and threshold
 * from `rule_meta`, the claim boundary from `claims.py`. Nothing in the
 * component that renders this decides what any of it means, which is what lets
 * the same screen serve a domain the code has never seen.
 */
export interface RaisedBy {
  id: string
  /** The rule's own name; the engine id is a last resort, never a label. */
  rule: string
  text: string
  severity: 'high' | 'medium' | 'low' | null
  threshold: string
  threshold_type: string
  threshold_status: string
  method: string
  factors: string[]
}

export interface EvidencePack {
  factor: string
  name: string
  state: string
  publisher: string
  endpoint: string
  dataset: string
  licence: string
  attribution: string
  runtime: string
  assessed_at: string
  methods: string[]
  measurements: {
    rule: string
    rule_name: string
    threshold: string
    evidence: Record<string, string | number>
  }[]
}

export interface InvestigationWorkspaceEntry {
  id: string
  name: string
  blurb: string
  next_step: string
  priority: string
  raised_by: RaisedBy[]
  established: string[]
  not_established: string[]
  evidence: EvidencePack[]
}
