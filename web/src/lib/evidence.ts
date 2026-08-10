import type { EvidenceEntry, EvidenceFinding } from '../types'

/**
 * Evidence explorer — presentation logic.
 *
 * Pure and deliberately incurious, for the same reason as `lib/historical.ts`:
 * every state on this screen was decided by the engine, and a component that
 * computes nothing is easy to claim and hard to prove. These functions can be
 * fed a payload whose numbers contradict its state and asserted to follow the
 * state.
 *
 * The explorer is the screen a professional studies hardest — it is where they
 * go to decide whether to trust a number — so it is also the screen where an
 * invented reassurance would do the most damage.
 */

const STATE_LABEL: Record<string, string> = {
  flagged: 'Flagged',
  clear: 'Checked · clear',
  informational: 'Informational',
  not_assessed: 'Not assessed',
}

/** Why a factor was not assessed, in the words the server chose. The three
 *  causes have three different fixes and rewriting them here would be the UI
 *  forming its own opinion about what went wrong. */
const REASON_LABEL: Record<string, string> = {
  not_selected: 'not loaded',
  demo_data: 'no live source',
  no_data: 'no usable observation',
}

export function stateLabel(entry: EvidenceEntry): string {
  const base = STATE_LABEL[entry.state] ?? STATE_LABEL.not_assessed
  const reason = entry.reason ? REASON_LABEL[entry.reason] : ''
  return reason ? `${base} · ${reason}` : base
}

export function stateClass(entry: EvidenceEntry): string {
  return `is-${entry.state}`
}

/**
 * What the explorer shows for this state.
 *
 * The section list is derived from the state rather than from whether a field
 * happens to be populated, so each state renders a deliberate shape:
 *
 * - **flagged** — measurement → threshold → finding → investigation
 * - **clear** — measurement → threshold → why nothing was crossed
 * - **informational** — measurement → methodology → source, and *no threshold*,
 *   because inventing one is exactly what this state must not do
 * - **not assessed** — what was attempted, and why it produced nothing
 *
 * Driving it from the state is what stops an informational entry growing a
 * threshold block the moment some unrelated payload field is non-empty.
 */
export interface SectionPlan {
  measurement: boolean
  threshold: boolean
  investigation: boolean
}

export function sections(entry: EvidenceEntry): SectionPlan {
  const measured = entry.state === 'flagged' || entry.state === 'clear'
    || entry.state === 'informational'
  return {
    measurement: measured,
    // Never for informational: no threshold was applied, and showing an empty
    // threshold block implies one exists and was met.
    threshold: entry.state === 'flagged' || entry.state === 'clear',
    investigation: entry.investigations.length > 0,
  }
}

/** The rows of a finding's evidence block, in the server's own key order.
 *  Not re-sorted and not filtered to the interesting ones — deciding which
 *  evidence matters is the reader's job. */
export function evidenceRows(finding: EvidenceFinding): [string, string][] {
  return Object.entries(finding.evidence ?? {}).map(
    ([k, v]) => [humanKey(k), String(v)])
}

/** Index names that are acronyms and read as typos when sentence-cased —
 *  "Ndvi" in a provenance table looks like a bug in the product. */
const ACRONYMS = new Set(['ndvi', 'evi', 'savi', 'msavi', 'gndvi', 'ndmi',
                          'nbr', 'ndbi', 'ndwi', 'lst', 'r2', 't'])

/** `baseline_period` → `Baseline period`. Formatting only. */
export function humanKey(key: string): string {
  return key.split('_')
    .map((w, i) => ACRONYMS.has(w.toLowerCase())
      ? w.toUpperCase()
      : i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)
    .join(' ')
}

/**
 * The four provenance rows, always in this order, always all four.
 *
 * A missing value renders as an em dash rather than vanishing. "Publisher: —"
 * is a readable statement about what Contour knows; a row that disappears is
 * indistinguishable from a row nobody thought to add, and the point of this
 * section is that the reader can see the shape of what is known.
 */
export function sourceRows(entry: EvidenceEntry): [string, string][] {
  const s = entry.source
  return [
    ['Publisher', s.publisher || '—'],
    ['Endpoint', s.endpoint || '—'],
    ['Licence', s.licence || '—'],
    ['Runtime verification', runtimeLabel(s.runtime)],
  ]
}

/** Plain words for the runtime state. `verified` means verified *in this
 *  process* (EM5) — a deployment with no credentials implements a factor and
 *  can prove none of it. */
export function runtimeLabel(runtime: string): string {
  switch (runtime) {
    case 'verified': return 'Verified live'
    case 'written': return 'Implemented, not yet run live'
    case 'generated': return 'No live implementation — demo data'
    case 'not_loaded': return 'Not loaded into this analysis'
    default: return 'Unknown'
  }
}

/**
 * Entries in the order the server sent them, optionally narrowed to one state.
 *
 * Not sorted by severity. The explorer opens on a specific factor, and a list
 * that reorders itself by how alarming each row is would rank the evidence —
 * which is the radar's job, done once, with a rule.
 */
export function orderedEntries(entries: EvidenceEntry[] | undefined,
                               state?: string): EvidenceEntry[] {
  if (!entries) return []
  return state ? entries.filter((e) => e.state === state) : entries
}

export function findEntry(entries: EvidenceEntry[] | undefined,
                          factor: string | null): EvidenceEntry | null {
  if (!entries || !factor) return null
  return entries.find((e) => e.factor === factor) ?? null
}
