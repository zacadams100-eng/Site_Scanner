import type { InvestigationWorkspaceEntry } from '../types'

/**
 * Investigation workspace — presentation logic.
 *
 * **This module must not know which domain it is rendering.** Every label that
 * names a thing in the world arrives as data: the investigation's name, the
 * rule's name, the threshold and its status, the publisher. What is written
 * here is only the *structure* of the question a professional asks, which is
 * the same in every domain:
 *
 *     why am I seeing this · what does it establish · what does it not ·
 *     what prompted it · what should be checked · what do I take along
 *
 * `investigation.test.ts` proves it by rendering a coastal investigation
 * assembled from fabricated metadata. If that test ever needs a change here to
 * pass, the abstraction has been broken and the diff is the evidence.
 */

/** Section headings, in the order a professional asks them. Domain-neutral by
 *  construction: none of these words names a thing in the world. */
export const SECTIONS = [
  { key: 'raised', title: 'Why this appeared' },
  { key: 'establishes', title: 'What this establishes' },
  { key: 'limits', title: 'What this does not establish' },
  { key: 'check', title: 'Suggested professional check' },
  { key: 'pack', title: 'Evidence to take to the professional' },
] as const

/** Priority as the engine ranked it. Read, never derived — the promotion rule
 *  depends on which factors the flags rest on, and a second opinion about
 *  urgency is exactly what EM11 forbids. */
export function priorityLabel(entry: InvestigationWorkspaceEntry): string {
  return entry.priority || 'unranked'
}

export function priorityClass(entry: InvestigationWorkspaceEntry): string {
  return `is-${entry.priority || 'unranked'}`
}

/**
 * "Raised by 2 findings" — or the singular, which matters more than it looks.
 *
 * A workspace that says "raised by 1 findings" reads as unproofed software in
 * the one screen where a professional is deciding whether to trust the output.
 */
export function raisedSummary(entry: InvestigationWorkspaceEntry): string {
  const n = entry.raised_by.length
  return `Raised by ${n} finding${n === 1 ? '' : 's'}`
}

/** The methods behind an investigation, deduplicated and stable. A reader
 *  quoting a figure needs the method version that produced it. */
export function methodsUsed(entry: InvestigationWorkspaceEntry): string[] {
  const out: string[] = []
  for (const pack of entry.evidence) {
    for (const m of pack.methods) if (m && !out.includes(m)) out.push(m)
  }
  return out
}

/** Whether every source behind this investigation was actually reached live.
 *  A statement about the evidence, never about the subject. */
export function allVerified(entry: InvestigationWorkspaceEntry): boolean {
  return entry.evidence.length > 0
    && entry.evidence.every((p) => p.runtime === 'verified')
}

/** `retreat_m` → `Retreat m`. Formatting only, and deliberately not a lookup
 *  table: a table would need an entry per domain, which is the coupling this
 *  module exists to avoid. */
export function humanKey(key: string): string {
  const s = key.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function findEntry(
  workspace: InvestigationWorkspaceEntry[] | undefined,
  id: string | null,
): InvestigationWorkspaceEntry | null {
  if (!workspace || !id) return null
  return workspace.find((w) => w.id === id) ?? null
}

/**
 * Why a check could not run, in words.
 *
 * The four causes stay separate because they have four different fixes and
 * four different owners. Collapsing them into "unavailable" is the specific
 * loss this product works hardest to prevent.
 */
const GAP_LABEL: Record<string, string> = {
  not_selected: 'not loaded into this report',
  demo_data: 'no live source — demo data cannot support a finding',
  no_data: 'source queried; no usable observation returned',
  insufficient: 'insufficient evidence to evaluate',
}

export function gapLabel(reason: string): string {
  return GAP_LABEL[reason] ?? 'not assessed'
}

/**
 * "4 checks could not run" — or nothing, when every check ran.
 *
 * The empty case returns a positive statement rather than an empty string,
 * because a section that vanishes when there is nothing to report is
 * indistinguishable from a section nobody implemented.
 */
export function gapSummary(entry: InvestigationWorkspaceEntry): string {
  const n = entry.gaps.length
  if (n === 0) return 'Every check behind this investigation ran.'
  return `${n} check${n === 1 ? '' : 's'} that would have informed this could not run`
}

/** The date the assessment ran, formatted. Empty rather than "Invalid Date". */
export function assessedOn(entry: InvestigationWorkspaceEntry): string {
  if (!entry.assessed_at) return ''
  const d = new Date(entry.assessed_at)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-GB',
    { day: 'numeric', month: 'short', year: 'numeric' })
}
