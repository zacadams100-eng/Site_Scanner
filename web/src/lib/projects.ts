/**
 * Projects — what the gallery lists, and what "open" restores.
 *
 * The old `SavedAoi` stored a boundary and nothing else, which was fine for a
 * dropdown of shapes but not for a home screen. Reopening one dropped whatever
 * factors you had chosen and put you back at the latest month, so a "saved
 * site" was really only a saved *outline*. A project carries the whole working
 * state: the shape, the factors, and where you were in time.
 *
 * Storage is localStorage, deliberately. These are one person's working set,
 * not shared documents — there is no account to hang them off, and a project
 * is small (a polygon and a dozen ids). The permalink remains the mechanism
 * for handing a view to someone else.
 */

export const PROJECTS_KEY = 'site-scanner.projects'

/** The pre-gallery key. Read once for migration, never written again. */
export const LEGACY_KEY = 'site-scanner.saved-aois'

const MAX_PROJECTS = 60

export interface Project {
  id: string
  name: string
  geometry: GeoJSON.Polygon
  area_ha: number
  /** Factor ids to restore on open. */
  factors: string[]
  /**
   * Timeline position to restore, or null for "wherever the latest data is".
   * Null rather than a number because step indices are only meaningful against
   * a given catalogue: if the catalogue grows a month, a stored 179 silently
   * becomes the wrong date, whereas null always means "most recent".
   */
  timeIndex: number | null
  createdAt: number
  updatedAt: number
}

/** What a legacy entry looked like. Only what the migration reads. */
interface LegacyAoi {
  id?: unknown
  name?: unknown
  geometry?: unknown
  area_ha?: unknown
  savedAt?: unknown
}

function isPolygon(g: unknown): g is GeoJSON.Polygon {
  if (!g || typeof g !== 'object') return false
  const p = g as GeoJSON.Polygon
  return p.type === 'Polygon' && Array.isArray(p.coordinates) && p.coordinates.length > 0
}

/**
 * Accepts anything and returns only what is structurally a project.
 *
 * localStorage is user-writable and survives across versions, so a shape read
 * from it is untrusted input. One malformed entry must not take the gallery
 * down with it — hence filtering rather than throwing.
 */
export function coerceProjects(raw: unknown, fallbackFactors: string[]): Project[] {
  if (!Array.isArray(raw)) return []
  const out: Project[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const p = item as Partial<Project> & LegacyAoi
    if (!isPolygon(p.geometry)) continue

    const saved = typeof p.savedAt === 'number' ? p.savedAt : undefined
    const created = typeof p.createdAt === 'number' ? p.createdAt : saved ?? Date.now()

    out.push({
      id: typeof p.id === 'string' && p.id ? p.id : `p${created}-${out.length}`,
      name: typeof p.name === 'string' && p.name.trim() ? p.name.trim() : 'Untitled site',
      geometry: p.geometry,
      area_ha: typeof p.area_ha === 'number' && isFinite(p.area_ha) ? p.area_ha : 0,
      // A legacy entry has no factor list; it opens with whatever the app's
      // defaults are rather than with nothing selected.
      factors: Array.isArray(p.factors) && p.factors.every((f) => typeof f === 'string') && p.factors.length
        ? (p.factors as string[])
        : fallbackFactors,
      timeIndex: typeof p.timeIndex === 'number' ? p.timeIndex : null,
      createdAt: created,
      updatedAt: typeof p.updatedAt === 'number' ? p.updatedAt : created,
    })
  }
  return out
}

/**
 * Load the gallery, migrating the pre-gallery list on first run.
 *
 * The legacy key is read but never cleared. Migration writes to a new key, so
 * rolling back to a build without the gallery still finds the old saves where
 * it left them — worth the few stale bytes.
 */
export function loadProjects(fallbackFactors: string[]): Project[] {
  let stored: Project[] = []
  try {
    stored = coerceProjects(JSON.parse(localStorage.getItem(PROJECTS_KEY) ?? '[]'), fallbackFactors)
  } catch {
    stored = []
  }
  if (stored.length) return sortProjects(stored)

  let legacy: Project[] = []
  try {
    legacy = coerceProjects(JSON.parse(localStorage.getItem(LEGACY_KEY) ?? '[]'), fallbackFactors)
  } catch {
    legacy = []
  }
  if (legacy.length) persistProjects(legacy)
  return sortProjects(legacy)
}

export function persistProjects(list: Project[]): void {
  try {
    localStorage.setItem(PROJECTS_KEY, JSON.stringify(list.slice(0, MAX_PROJECTS)))
  } catch {
    /* Storage full or blocked. Saving is a convenience, not a guarantee, and
       failing here must not take the open project down with it. */
  }
}

/** Most recently worked on first — the order a home screen wants. */
export function sortProjects(list: Project[]): Project[] {
  return [...list].sort((a, b) => b.updatedAt - a.updatedAt)
}

/**
 * "Copy", "Copy 2", "Copy 3" — the duplicate never collides with a name
 * already in the gallery, so two cards are never indistinguishable.
 */
export function copyName(name: string, existing: string[]): string {
  const taken = new Set(existing)
  const base = `${name} copy`
  if (!taken.has(base)) return base
  for (let n = 2; n < 1000; n++) {
    const candidate = `${base} ${n}`
    if (!taken.has(candidate)) return candidate
  }
  return base
}

/**
 * The polygon as an SVG path, fitted to a box.
 *
 * A project's thumbnail is its outline — no tiles, no canvas snapshot, nothing
 * extra in storage. It is derived from geometry we already hold, so it renders
 * instantly, offline, and identically every time. A screenshot would look
 * richer and would also mean waiting on a tile server to draw a list.
 *
 * Latitude is flipped (SVG y grows downward) and the aspect ratio is preserved
 * so a long thin site still reads as long and thin. Longitude is not corrected
 * for the cos(latitude) convergence: at the scale of a single site the error is
 * imperceptible, and the shapes are recognised by proportion, not measured.
 */
export function thumbnailPath(
  geometry: GeoJSON.Polygon,
  box: { width: number; height: number; pad?: number },
): string {
  const ring = geometry.coordinates?.[0]
  if (!ring || ring.length < 3) return ''

  const pad = box.pad ?? 6
  const xs = ring.map((c) => c[0])
  const ys = ring.map((c) => c[1])
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)

  const spanX = maxX - minX
  const spanY = maxY - minY
  const innerW = box.width - pad * 2
  const innerH = box.height - pad * 2

  // A degenerate span would divide by zero. One shared scale keeps the aspect
  // ratio; centring offsets absorb whichever axis has slack.
  const scale = Math.min(
    spanX > 0 ? innerW / spanX : Infinity,
    spanY > 0 ? innerH / spanY : Infinity,
  )
  const s = isFinite(scale) && scale > 0 ? scale : 1

  const offX = pad + (innerW - spanX * s) / 2
  const offY = pad + (innerH - spanY * s) / 2

  const pts = ring.map((c) => {
    const x = offX + (c[0] - minX) * s
    // Flip: north should be up.
    const y = offY + (maxY - c[1]) * s
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  return `M${pts.join('L')}Z`
}

/** "just now", "6 min ago", "3 days ago" — relative is what a gallery wants. */
export function relativeTime(then: number, now = Date.now()): string {
  const secs = Math.max(0, Math.round((now - then) / 1000))
  if (secs < 45) return 'just now'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} hr ago`
  const days = Math.round(hours / 24)
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  const months = Math.round(days / 30)
  if (months < 12) return `${months} mo ago`
  return `${Math.round(months / 12)} yr ago`
}
