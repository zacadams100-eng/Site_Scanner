/**
 * The portfolio view's data and display rules.
 *
 * Kept out of the component so the rules about *what a portfolio row may claim*
 * are testable without rendering. The component decides how a row looks; this
 * decides what it says and how the rows are counted.
 *
 * ## The rule that shapes everything here
 *
 * A portfolio mistake is not visible the way a single-site mistake is. A
 * professional reading one report sees the gaps; a reader of a portfolio sees a
 * number, applies it to a thousand sites, and has no way to check it. So the
 * counts a reader acts on are the counts the backend supplied, and this module
 * derives nothing beyond formatting.
 *
 * Specifically: **there is no computed total, average, percentage or index
 * anywhere in this file.** The one derived value is `attention`, which is a
 * partition of rows into named buckets — and every row still shows the counts
 * that put it in its bucket.
 */

import type { PortfolioDocument, PortfolioRadar, PortfolioRow } from '../types'

export async function fetchDemoPortfolio(signal?: AbortSignal): Promise<PortfolioDocument> {
  const res = await fetch('/api/portfolio/demo', { signal })
  if (!res.ok) throw new Error(`Portfolio unavailable (${res.status})`)
  return res.json()
}

/**
 * The radar, as the tiles that get rendered.
 *
 * Order is the argument. `sites` first because it is the denominator;
 * **`sites_unassessed` second, before any finding count**, because a reader who
 * meets "12 with findings" before "6 never scanned" has already formed a view
 * of the portfolio. This is the same editorial rule the Brief follows for
 * coverage-before-findings, applied at portfolio scale where the mistake is
 * made once and applied to every site.
 *
 * Each tile carries a `note` saying what the number does *not* mean, because a
 * large figure on a dark tile is the most quotable thing on the screen and it
 * will be quoted without its column heading.
 */
export interface RadarTile {
  key: string
  label: string
  value: number
  note: string
  /** `gap` tiles are the ones that describe what is *not* known. They are
   *  rendered with the same weight as the findings, never smaller. */
  kind: 'count' | 'gap' | 'attention'
}

export function radarTiles(radar: PortfolioRadar | null | undefined): RadarTile[] {
  if (!radar) return []
  return [
    {
      key: 'sites', label: 'Sites', value: radar.sites, kind: 'count',
      note: 'On the books. Not all have been assessed.',
    },
    {
      key: 'unassessed', label: 'Never scanned', value: radar.sites_unassessed,
      kind: 'gap',
      note: 'Nothing has been established about these. They are not clear — they are unexamined.',
    },
    {
      key: 'findings', label: 'Sites with findings',
      value: radar.sites_with_findings, kind: 'attention',
      note: 'At least one check crossed a reporting threshold. Not a judgement about the site.',
    },
    {
      key: 'investigations', label: 'Investigations open',
      value: radar.investigations, kind: 'attention',
      note: 'Professional follow-up the findings prompt. Not advice on any site.',
    },
    {
      key: 'gaps', label: 'Evidence gaps', value: radar.evidence_gaps,
      kind: 'gap',
      note: 'Checks that could not run, plus parts of a scanner’s subject with no checks at all.',
    },
    {
      key: 'review', label: 'Awaiting review', value: radar.awaiting_review,
      kind: 'attention',
      note: 'Sites with findings that no professional has reviewed. Currently every one of them.',
    },
  ]
}

/**
 * Which bucket a row belongs in, and it is a partition rather than a ranking.
 *
 * The distinction matters: a rank implies an ordering along one dimension,
 * which is a score with the number hidden. These are three different *kinds* of
 * work — something to look at, something not yet looked at, and something
 * looked at with nothing found — and a reader chooses which to spend time on.
 */
export type Attention = 'findings' | 'unassessed' | 'quiet'

export function attentionOf(row: PortfolioRow): Attention {
  if (row.findings > 0) return 'findings'
  if (!row.assessed) return 'unassessed'
  return 'quiet'
}

export const ATTENTION_LABEL: Record<Attention, string> = {
  findings: 'Has findings',
  unassessed: 'Never scanned',
  quiet: 'Nothing flagged',
}

/** What the bucket means, at the length a reader will actually read.
 *
 *  `quiet` is the one that has to be exactly right. "Nothing flagged" is a
 *  statement about the checks that ran, not about the site, and the sentence
 *  says so — this is the portfolio-scale version of the distinction the whole
 *  product rests on. */
export const ATTENTION_NOTE: Record<Attention, string> = {
  findings: 'A check crossed a reporting threshold. What it establishes, and what it does not, is in the record.',
  unassessed: 'On the books, never scanned. Nothing has been established about these sites either way.',
  quiet: 'Assessed, with nothing crossing a threshold in the checks that ran. Not a statement that the site is sound — the evidence gaps column says what was not asked.',
}

/** Rows grouped by bucket, in the order the backend already sorted them.
 *
 *  Never re-sorted here. The backend's ordering shows findings first, then
 *  unassessed, then the rest, and re-deriving it in the frontend would be a
 *  second opinion about what needs attention. */
export function groupRows(rows: PortfolioRow[]): { attention: Attention; rows: PortfolioRow[] }[] {
  const order: Attention[] = ['findings', 'unassessed', 'quiet']
  return order
    .map((attention) => ({ attention, rows: rows.filter((r) => attentionOf(r) === attention) }))
    .filter((g) => g.rows.length > 0)
}

/** The date a row last had anything established about it, or a statement that
 *  nothing has been. Never an em-dash or a blank: an empty cell in a date
 *  column reads as a rendering fault rather than as a fact. */
export function lastAssessed(row: PortfolioRow): string {
  if (!row.assessed) return 'Never'
  if (!row.last_assessed) return 'Date not recorded'
  const d = new Date(row.last_assessed)
  if (Number.isNaN(d.getTime())) return 'Date not recorded'
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
