/**
 * The scanner library's structure.
 *
 * Pulled out of the component so the rules about *what the library may claim*
 * are testable without rendering anything. The component decides how a section
 * looks; this decides what is in it and what each entry is allowed to say.
 *
 * ## The one rule
 *
 * **Everything here comes from the registry.** There is no roadmap array, no
 * grouping table and no availability list in the frontend. A second
 * description of the product's shape drifts from the backend's, and the
 * frontend's copy is the one nobody remembers to update — the first symptom
 * would be a card offering a scanner the API refuses.
 *
 * That is why `sections()` reads `catalog.families` rather than grouping by
 * `scanner.family` itself: the backend already decided both the grouping and
 * the order, and re-deriving it here would be a second opinion.
 *
 * ## Why `status` matters more than `implemented`
 *
 * `implemented` is binary and it is not enough. Three of the four built
 * scanners cover *part* of their subject, and a card reading "Water ·
 * available" invites a user to read a clear result as "no water issues" when
 * it means "no flood, surface water or coastal issues — groundwater, drainage
 * and catchment were never asked".
 *
 * So a partial scanner shows what it covers and what it does not, in the
 * library, before the user picks it. Finding out afterwards is finding out too
 * late.
 */

import type { Catalog, ScannerDomain, ScannerFamily, ScannerInfo } from '../types'

/** How a scanner presents its readiness. Ordered from most to least capable,
 *  which is the order the library sorts within a family. */
export type ScannerStatus = 'live' | 'partial' | 'planned'

const STATUS_ORDER: Record<ScannerStatus, number> = {
  live: 0, partial: 1, planned: 2,
}

/** What the badge says, and it is deliberately not "available".
 *
 *  "Available" answers "can I click it", which is the least useful of the
 *  questions a reader has. These answer "what will it tell me". */
export const STATUS_LABEL: Record<ScannerStatus, string> = {
  live: 'Complete',
  partial: 'Partial coverage',
  planned: 'Not built',
}

/** One line under the badge, saying what the status means for a result.
 *
 *  The partial wording is the load-bearing one in this file. It is the
 *  sentence that stops a clear result being read as a clean site. */
export const STATUS_NOTE: Record<ScannerStatus, string> = {
  live: 'Every part of this scanner’s subject has checks behind it.',
  partial: 'Some parts of this subject have no checks yet. A clear result covers only the parts that were assessed — the rest were never asked.',
  planned: 'Registered so the roadmap has one source of truth. It cannot assess anything, and the API refuses it.',
}

export function statusOf(scanner: ScannerInfo): ScannerStatus {
  // Falls back rather than assuming: a backend predating `status` still
  // renders, and the fallback is the cautious reading — implemented but
  // undescribed is `partial`, never `live`, because claiming complete coverage
  // on a scanner that never said so is the error that misleads.
  if (scanner.status) return scanner.status
  return scanner.implemented ? 'partial' : 'planned'
}

export function isOpenable(scanner: ScannerInfo): boolean {
  return statusOf(scanner) !== 'planned'
}

export function builtDomains(scanner: ScannerInfo): ScannerDomain[] {
  return (scanner.domains ?? []).filter((d) => d.implemented)
}

/** The gap, named. Every entry has a `blocked_by` — the backend refuses to
 *  register one without it. */
export function domainGaps(scanner: ScannerInfo): ScannerDomain[] {
  return (scanner.domains ?? []).filter((d) => !d.implemented)
}

export interface LibrarySection {
  family: ScannerFamily
  scanners: ScannerInfo[]
  /** Whether anything in this section can actually be opened. A section of
   *  entirely unbuilt scanners is a roadmap, and the library says so rather
   *  than presenting it identically to one that works. */
  openable: boolean
}

/**
 * The library's sections, in the backend's order.
 *
 * Scanners within a family sort by status — what works first — and then by the
 * registry's own order, which is stable. A family the backend sent with no
 * scanners is dropped rather than rendered empty: an empty section is a
 * heading that promises something below it.
 */
export function sections(catalog: Catalog | null | undefined): LibrarySection[] {
  const scanners = catalog?.scanners ?? []
  if (scanners.length === 0) return []

  const byId = new Map(scanners.map((s) => [s.id, s]))
  const families = catalog?.families ?? []

  // No families from the backend — an older one, or a deployment mid-upgrade.
  // One ungrouped section rather than invented families: the library still
  // works and claims nothing about a structure it was not told about.
  if (families.length === 0) {
    return [{
      family: { id: 'all', name: 'Scanners', subject: '', scanners: scanners.map((s) => s.id) },
      scanners: [...scanners].sort(byStatusThenRegistry(scanners)),
      openable: scanners.some(isOpenable),
    }]
  }

  const out: LibrarySection[] = []
  for (const family of families) {
    const members = family.scanners
      .map((id) => byId.get(id))
      .filter((s): s is ScannerInfo => Boolean(s))
      .sort(byStatusThenRegistry(scanners))
    if (members.length === 0) continue
    out.push({ family, scanners: members, openable: members.some(isOpenable) })
  }
  return out
}

function byStatusThenRegistry(all: ScannerInfo[]) {
  const index = new Map(all.map((s, i) => [s.id, i]))
  return (a: ScannerInfo, b: ScannerInfo) => {
    const byStatus = STATUS_ORDER[statusOf(a)] - STATUS_ORDER[statusOf(b)]
    if (byStatus !== 0) return byStatus
    return (index.get(a.id) ?? 0) - (index.get(b.id) ?? 0)
  }
}

/** The platform's shape in one line, counted from the registry so it cannot
 *  claim more than exists. */
export function tally(catalog: Catalog | null | undefined) {
  const scanners = catalog?.scanners ?? []
  const count = (s: ScannerStatus) =>
    scanners.filter((x) => statusOf(x) === s).length
  return {
    scanners: scanners.length,
    live: count('live'),
    partial: count('partial'),
    planned: count('planned'),
    families: (catalog?.families ?? []).length,
    /** Everything that can be opened — live and partial together. */
    openable: scanners.filter(isOpenable).length,
  }
}
