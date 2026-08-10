import type { HistoricalEntry } from '../types'

/**
 * Presentation helpers for the historical panel.
 *
 * Every function here is pure, and every one of them is deliberately stupid.
 * `EVIDENCE_MODEL.md` EM11: the UI renders the state the engine decided and
 * never derives one.
 *
 * These live in `lib/` rather than inside the component specifically so they
 * can be tested hostilely — fed a payload whose numbers contradict its state,
 * and asserted to follow the state. A component that computes nothing is easy
 * to claim and hard to prove; a function that ignores `change_pct` when
 * choosing a label can be proven in three lines.
 */

/** What the user reads for each state. The vocabulary is the radar's, because
 *  a user should not have to learn a second one for satellite evidence. */
const STATE_LABEL: Record<string, string> = {
  flagged: 'Flagged',
  clear: 'Checked · clear',
  informational: 'Informational',
  not_assessed: 'Not assessed',
}

/**
 * The label for an entry.
 *
 * Reads `finding.state` and nothing else. It does not look at `change_pct`,
 * and a test feeds it a −45% change with a `clear` state to prove it: the
 * temptation is to notice that −45% is "obviously" a flag, and noticing is
 * exactly what a UI must not do.
 */
export function findingLabel(entry: HistoricalEntry): string {
  const state = entry.finding?.state
  if (!state) return STATE_LABEL.not_assessed
  return STATE_LABEL[state] ?? STATE_LABEL.not_assessed
}

/** The modifier class. Same rule: derived from the state, never the number. */
export function findingClass(entry: HistoricalEntry): string {
  return `is-${entry.finding?.state ?? 'not_assessed'}`
}

/**
 * Why this entry could not be assessed, in the words the server chose.
 *
 * The server distinguishes `no_data` (asked, nothing usable came back) from
 * `demo_data` (generated) from `not_selected` (never loaded), and each has a
 * different fix. Rewriting them here would be the UI forming its own opinion
 * about what went wrong.
 */
export function unavailableReason(entry: HistoricalEntry): string {
  if (entry.finding?.state !== 'not_assessed') return ''
  if (entry.finding?.text) return entry.finding.text
  if (!entry.available) return 'This layer is not in the report.'
  return entry.metric?.shortfall || 'Not assessed.'
}

/** Change as a signed string, or the absolute difference where the baseline is
 *  zero and a percentage would be undefined. Formatting only — the server
 *  decided which of the two applies. */
export function changeText(entry: HistoricalEntry): string {
  const m = entry.metric
  if (!m || m.change === null || m.change === undefined) return '—'
  if (m.change_type === 'absolute' || m.change_pct === null
      || m.change_pct === undefined) {
    const sign = m.change > 0 ? '+' : ''
    return `${sign}${m.change.toFixed(3)} (absolute)`
  }
  const sign = m.change_pct > 0 ? '+' : ''
  return `${sign}${m.change_pct.toFixed(1)}%`
}

/** "13 of 15 years observed", or nothing when there is no coverage to state. */
export function coverageText(entry: HistoricalEntry): string {
  const m = entry.metric
  if (!m || !m.years_total) return ''
  return `${m.years_usable} of ${m.years_total} years observed`
}

/** The period a value was measured over, e.g. "2011–2013". */
export function periodText(years: number[] | undefined): string {
  if (!years || !years.length) return '—'
  return years.length === 1
    ? String(years[0])
    : `${years[0]}–${years[years.length - 1]}`
}

/**
 * Entries in the order the server sent them.
 *
 * Not sorted by severity, and not filtered to the interesting ones. Both would
 * be the UI deciding which evidence matters — and hiding a `clear` result is
 * how "we checked" becomes indistinguishable from "we could not look".
 */
export function orderedEntries(entries: HistoricalEntry[]): HistoricalEntry[] {
  return entries
}
