import { create } from 'zustand'
import type { Catalog, Cell, DrawMode, Factor, Marker, SeriesResponse } from './types'
import { fetchCells, fetchSeries } from './api'
import { decodeState, writeUrl, type Template } from './lib/permalink'
import { openOnGallery } from './lib/home'
import { defaultFactors } from './lib/defaults'

/**
 * One store, and one rule that matters more than the rest:
 *
 *   `timeIndex` is the single source of truth for "when".
 *
 * The map, the timeline, the table and the charts all read it. None of them
 * keeps a copy. Every "the chart and the map disagree" bug comes from
 * violating that, so it is worth stating in the file rather than the wiki.
 */

const DEFAULT_FACTORS = ['ndvi', 'lc_tree_pct', 'precip_total', 'lst_day']
const MAX_FACTORS = 12
// Two is the minimum that is a comparison; four is where a reader stops being
// able to hold every column's coverage in their head at once. The API enforces
// the same bound. See COMPARISON_CONTRACT.md.
const MAX_COMPARE = 4
const SAVED_KEY = 'site-scanner.saved-aois'

/**
 * A saved site is a whole workspace, not just a shape.
 *
 * Reopening a site and finding the default four factors — with the timeline
 * back at the present — is the same amount of work as drawing it again, which
 * is to say the feature did not do anything. `factors`, `timeIndex` and
 * `compareIndex` are optional because entries written before this change do
 * not have them; those load their geometry and leave the rest of the view
 * alone, which is exactly what they used to do.
 */
/**
 * What actually happened on a site, recorded afterwards by the person who
 * found out.
 *
 * **Capture only.** Nothing aggregates these, nothing scores them, and nothing
 * derived from them appears anywhere in the product. The reason to store them
 * now is that the information is perishable — a planning decision or a survey
 * result is known once, by one person, and if there is nowhere to put it that
 * day it is gone. Whether it ever becomes a visible feature is a later
 * decision that this does not pre-empt.
 *
 * Free text on purpose. A dropdown of outcomes would be this product deciding
 * in advance what counts as a result, which is the same mistake as scoring a
 * site.
 */
export interface SiteOutcome {
  id: string
  /** What happened, in the recorder's own words. */
  note: string
  /** When it happened — not when it was typed. A planning decision from March
   *  recorded in August is a March fact. */
  occurredOn: string
  recordedAt: number
  /** Which scanner produced the assessment this outcome is about. */
  scanner: string
  /** The findings that were on the report when this was recorded.
   *
   *  Without them an outcome is unattached to anything: the report will be
   *  re-run against different data one day, and "the survey found nothing"
   *  only means something beside what the scan said at the time. */
  findingIds: string[]
  /** How much of the assessment had evidence behind it, as it stood. An
   *  outcome recorded against a report that could read almost nothing is a
   *  weaker signal than one recorded against a full assessment, and that
   *  context has to travel with it. */
  coverage?: { assessed: number; relevant: number }
}

/**
 * Who reviewed a report, if anyone has.
 *
 * **Absent by default and never populated by the product.** Scaffolding for a
 * co-signed brief, not a claim: an unfilled field says no one has reviewed
 * this, which is true of every report today.
 */
export interface SiteReview {
  name: string
  role: string
  reviewedOn: string
  recordedAt: number
}

export interface SavedAoi {
  id: string
  name: string
  geometry: GeoJSON.Polygon
  area_ha: number
  savedAt: number
  factors?: string[]
  timeIndex?: number
  compareIndex?: number | null
  markers?: Marker[]
  /** Optional and absent on every entry written before this existed. */
  outcomes?: SiteOutcome[]
  review?: SiteReview
}

/** What an exported sites file looks like. Versioned so a later format change
 *  can migrate rather than silently misread. */
export interface SitesFile {
  format: 'site-scanner.sites'
  version: 1
  exportedAt: string
  sites: SavedAoi[]
}

interface State {
  catalog: Catalog | null
  catalogError: string | null
  isMock: boolean

  aoi: GeoJSON.Polygon | null
  drawMode: DrawMode
  cells: Cell[]
  // Undo/redo over drawn shapes. A Procreate-like tool that cannot undo
  // breaks its own metaphor within about ten seconds of use.
  past: (GeoJSON.Polygon | null)[]
  future: (GeoJSON.Polygon | null)[]
  saved: SavedAoi[]
  /** Named points on the map. Saved with the workspace and exported with the
   *  shape, but never queried — a marker is a note, not an area. */
  markers: Marker[]

  selected: string[]
  data: SeriesResponse | null
  loading: boolean
  error: string | null

  timeIndex: number
  playing: boolean
  // Second time position. When set, the UI switches to comparison mode:
  // "what changed between these two dates" is the most common real question
  // in temporal GIS, and in ArcGIS it is a multi-step raster-calculator chore.
  compareIndex: number | null

  activeTab: 'overview' | 'radar' | 'findings' | 'table' | 'charts' | 'sources'
  browserOpen: boolean

  /**
   * The active scanner's id, and whether the library is showing.
   *
   * The scanner is the product vertical; the site is the thing being analysed.
   * `scannerId` is the only scanner state the frontend holds — everything else
   * about a scanner (its name, subject, availability, factors) comes from
   * `/api/catalog`, so there is no second source of truth to drift.
   */
  scannerId: string
  library: boolean
  setLibrary: (o: boolean) => void
  chooseScanner: (id: string) => void

  /** Which factor the evidence explorer is open on, or null. A factor id
   *  rather than a copy of the entry: the payload is the source of truth and a
   *  snapshot would go stale the moment the report refreshes. */
  evidenceFactor: string | null

  /** Which investigation the workspace is open on, or null. */
  investigationId: string | null

  sidebarOpen: boolean
  sidebarSection: 'layers' | 'templates' | 'sites' | 'data' | 'analysis'
  panelOpen: boolean
  /** How strongly the value overlay is painted over the basemap. A layer you
   *  cannot fade is a layer you cannot check against the ground beneath it. */
  overlayOpacity: number

  /** Live instrument readouts for the status bar. Held here rather than in
   *  MapCanvas because the bar is a sibling of the map, not a child. */
  cursor: { lng: number; lat: number } | null
  view: { zoom: number; scale: number } | null
  /** The site currently open, if it was loaded from a saved one — shown in the
   *  top bar the way a document name is. */
  projectName: string | null

  /**
   * Gallery or workspace — which of the frame's two modes is showing.
   *
   * The gallery takes the whole window rather than sitting in the report
   * panel, because a home screen occupying 440px beside a map that has nothing
   * to show is two half-answers. The map is not unmounted underneath it: the
   * gallery is an overlay, so MapLibre keeps its GL context, its tiles and its
   * position, and opening a site is instant rather than a re-initialisation.
   */
  home: boolean
  setHome: (o: boolean) => void

  /** Sites picked for evidence comparison, in the order the user picked them.
   *
   *  Order is preserved deliberately and never sorted — any ordering by count
   *  is a ranking, and ranking is what EM10 forbids. Capped at four by the
   *  comparison contract. */
  compareIds: string[]
  setCompareIds: (ids: string[]) => void
  toggleCompare: (id: string) => void
  /** Whether the comparison screen is open.
   *
   *  Separate from `compareIds` because picking must never navigate. Deriving
   *  "open" from "two are picked" meant checking the second box swapped the
   *  gallery for the comparison mid-selection, so a third site could not be
   *  picked at all. Selection and navigation are different intents. */
  comparing: boolean
  setComparing: (o: boolean) => void

  /**
   * A pending map move, consumed by MapCanvas.
   *
   * The map instance lives inside MapCanvas and nothing else can reach it, so
   * "go to this place" travels as state rather than as a call. `nonce` is what
   * makes searching for the same place twice move the map twice — without it
   * the second request is an identical object and the effect never re-runs.
   */
  flyTo: { lng: number; lat: number; zoom: number; nonce: number } | null
  goTo: (lng: number, lat: number, zoom?: number) => void

  setCatalog: (c: Catalog) => void
  setCatalogError: (e: string | null) => void
  setMock: (m: boolean) => void
  setDrawMode: (m: DrawMode) => void
  setAoi: (g: GeoJSON.Polygon | null, opts?: { skipHistory?: boolean; keepProject?: boolean }) => void
  undo: () => void
  redo: () => void
  saveAoi: (name: string) => void
  loadSaved: (id: string) => void
  deleteSaved: (id: string) => void
  renameSaved: (id: string, name: string) => void
  /** Record what actually happened on a saved site. Capture only — nothing
   *  aggregates or scores these. */
  recordOutcome: (id: string, note: string, occurredOn: string) => void
  removeOutcome: (siteId: string, outcomeId: string) => void
  /** Attach or clear who reviewed a report. Never populated automatically. */
  setReview: (id: string, review: Omit<SiteReview, 'recordedAt'> | null) => void
  updateSaved: (id: string) => void
  importSites: (sites: SavedAoi[]) => number
  addMarker: (lng: number, lat: number, name?: string) => void
  renameMarker: (id: string, name: string) => void
  moveMarker: (id: string, lng: number, lat: number) => void
  removeMarker: (id: string) => void
  toggleFactor: (id: string) => void
  setSelected: (ids: string[]) => void
  applyTemplate: (t: Template) => void
  setTimeIndex: (i: number) => void
  setCompareIndex: (i: number | null) => void
  setPlaying: (p: boolean) => void
  setTab: (t: 'overview' | 'radar' | 'findings' | 'table' | 'charts' | 'sources') => void
  setBrowserOpen: (o: boolean) => void
  openEvidence: (factor: string) => void
  closeEvidence: () => void
  openInvestigation: (id: string) => void
  closeInvestigation: () => void
  setSidebarOpen: (o: boolean) => void
  setSidebarSection: (s: 'layers' | 'templates' | 'sites' | 'data' | 'analysis') => void
  setPanelOpen: (o: boolean) => void
  setOverlayOpacity: (o: number) => void
  setCursor: (c: { lng: number; lat: number } | null) => void
  setView: (v: { zoom: number; scale: number } | null) => void
  refresh: () => Promise<void>
  hydrateFromUrl: () => void
  syncUrl: () => void
}

let inflight: AbortController | null = null
// Incremented on every refresh request. A call whose generation is no longer
// the current one has been superseded and stops rather than resolving — a
// timer-based debounce that clears the pending timeout leaves its promise
// permanently unresolved, which quietly leaks one per keystroke.
let refreshGeneration = 0

/**
 * How long to wait for the user to stop changing their mind.
 *
 * Aborting an in-flight request already stops answers arriving out of order,
 * but the request has still been *sent* — toggling three factors fired three
 * round trips, two of which the server did the work for and nobody read. That
 * costs upstream quota and, now that the API is rate limited, some of the
 * user's own budget.
 *
 * 180ms is below the ~250ms at which a delay starts to feel like lag, and
 * comfortably above the gap between two deliberate clicks.
 */
const REFRESH_DEBOUNCE_MS = 180

/**
 * Don't land the user on a blank month.
 *
 * The default position is the most recent step, but an optical index in an
 * English December is a legitimate gap — so the first thing a new user would
 * see is an empty map and "no data", which reads as broken rather than as
 * honest. If the current step has no value for the primary factor, step back
 * to the most recent one that does.
 *
 * Only ever moves backwards, and only when the current position is empty, so
 * it never fights a deliberate scrub onto a gap the user is inspecting.
 */
function settleTime(data: SeriesResponse, selected: string[], current: number): number {
  const primary = data.series[selected[0]]
  if (!primary) return current
  const at = primary.points[current]
  if (!at || at.value !== null) return current
  for (let i = current - 1; i >= 0; i--) {
    if (primary.points[i]?.value !== null) return i
  }
  return current
}

function loadSaved(): SavedAoi[] {
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEY) ?? '[]')
  } catch {
    return []
  }
}

function persistSaved(list: SavedAoi[]): void {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify(list))
  } catch {
    /* storage full or blocked — saving is a convenience, not a guarantee */
  }
}

// Read once. `saved` and `home` are derived from the same list, and calling
// loadSaved() twice would let them disagree if storage changed in between.
const initialSaved = loadSaved()

export const useStore = create<State>((set, get) => ({
  catalog: null,
  catalogError: null,
  isMock: false,
  aoi: null,
  drawMode: null,
  cells: [],
  past: [],
  future: [],
  saved: initialSaved,
  markers: [],
  selected: DEFAULT_FACTORS,
  data: null,
  loading: false,
  error: null,
  timeIndex: 0,
  playing: false,
  compareIndex: null,
  // Overview first: a site's landing page is the briefing, not the toolset.
  // Radar answers "is there anything here I should worry about" and remains
  // one click away, but it opens mid-analysis — it assumes you already know
  // what was looked at. The overview states the evidence, what it prompts and
  // what could not be established, which is the order someone needs them in
  // when they have not seen this site before. Findings — what the numbers did
  // — stays the follow-up rather than the opener.
  activeTab: 'overview',
  browserOpen: false,
  evidenceFactor: null,
  scannerId: 'land',
  // Opens on the library: the first decision is which scanner, not which site.
  library: true,
  investigationId: null,
  // Open on a desktop, closed on a phone: at 390px the panel covers most of
  // the map, and a first-time tap on the map is far more likely to be a drawn
  // shape than a mis-tap on a section that was never asked for.
  sidebarOpen: typeof window === 'undefined' || window.innerWidth > 900,
  sidebarSection: 'layers',
  panelOpen: true,
  overlayOpacity: 0.72,
  cursor: null,
  view: null,
  projectName: null,
  flyTo: null,
  home: typeof window !== 'undefined' &&
    openOnGallery(initialSaved.length, window.location.hash),
  compareIds: [],
  comparing: false,

  // Searching for a place is a request to look at the map, so it leaves the
  // gallery. Without this the search box on the home screen flies a map the
  // user cannot see and reads as a dead control.
  goTo: (lng, lat, zoom = 14) =>
    set({ flyTo: { lng, lat, zoom, nonce: Date.now() }, home: false }),

  setCatalog: (c) => {
    // Land on the most recent step: users overwhelmingly want "now" first,
    // then scrub backwards to see how it got there. A URL overrides this.
    const fromUrl = decodeState(location.hash)
    // Only when the URL did not choose: a shared link's factor list is the
    // sender's analysis and must not be overwritten by a default.
    const opening = fromUrl.factors?.length
      ? get().selected
      : defaultFactors(c.factors.map((f) => f.id))
    set({
      catalog: c,
      selected: opening,
      timeIndex: fromUrl.t ?? Math.max(0, c.time.steps.length - 1),
    })
    get().hydrateFromUrl()
  },
  setLibrary: (o) => set({ library: o }),

  /**
   * Enter a scanner.
   *
   * Clears the drawn shape and the report: a site assessed by the land scanner
   * is not the same document as the same shape assessed by habitat, and
   * carrying the old report across would show one scanner's findings under
   * another's name. The map keeps its position, so the user does not lose
   * where they were looking.
   */
  chooseScanner: (id) => {
    if (id === get().scannerId) { set({ library: false }); return }
    set({
      scannerId: id, library: false, aoi: null, data: null, cells: [],
      error: null, evidenceFactor: null, investigationId: null,
      projectName: null, past: [], future: [],
    })
  },

  setCatalogError: (e) => set({ catalogError: e }),
  setMock: (m) => set({ isMock: m }),
  setDrawMode: (m) => {
    // Arming a tool on a narrow screen folds the sidebar away. Its panel is an
    // overlay there, covering most of the map — so "pick the marker tool, tap
    // the map" ended with the tap landing on the sidebar and nothing
    // happening, which reads as a broken tool.
    const narrow = typeof window !== 'undefined' && window.innerWidth <= 900
    set(m && narrow ? { drawMode: m, sidebarOpen: false } : { drawMode: m })
    // Arming a tool is a statement about the map, so it always leaves the
    // gallery. "Draw a new one" is the gallery's own primary button and this
    // is what makes it go somewhere.
    if (m) set({ home: false })
  },

  setHome: (o) => set({ home: o }),

  setCompareIds: (ids) => set({ compareIds: ids.slice(0, MAX_COMPARE) }),
  setComparing: (o) => set({ comparing: o }),
  toggleCompare: (id) => {
    const current = get().compareIds
    // Append rather than insert-sorted: the order the user picked is the only
    // order this app is allowed to have an opinion about.
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : [...current, id].slice(-MAX_COMPARE)
    // Unpicking below two closes an open comparison — it can no longer show
    // what it claims to show.
    set({ compareIds: next, comparing: get().comparing && next.length >= 2 })
  },

  setAoi: (g, opts) => {
    const { aoi, past } = get()
    set({
      aoi: g,
      drawMode: null,
      // A shape on the map is the workspace by definition. This is also what
      // dismisses the gallery when a card is opened, since loadSaved ends
      // here — one rule rather than one per entry point.
      home: g ? false : get().home,
      // Drawing somewhere else is a new site, not the saved one under a new
      // shape — so the document name goes with it unless we were told to keep
      // it (a restore, or an edit of the same site).
      projectName: opts?.keepProject ? get().projectName : null,
      // Cap the history so a long session cannot grow it without bound.
      past: opts?.skipHistory ? past : [...past, aoi].slice(-40),
      future: opts?.skipHistory ? get().future : [],
    })
    if (g) void get().refresh()
    else set({ data: null, cells: [], error: null })
    get().syncUrl()
  },

  undo: () => {
    const { past, aoi, future } = get()
    if (!past.length) return
    const prev = past[past.length - 1]
    set({ past: past.slice(0, -1), future: [aoi, ...future].slice(0, 40), aoi: prev })
    if (prev) void get().refresh()
    else set({ data: null, cells: [] })
  },

  redo: () => {
    const { future, aoi, past } = get()
    if (!future.length) return
    const next = future[0]
    set({ future: future.slice(1), past: [...past, aoi].slice(-40), aoi: next })
    if (next) void get().refresh()
    else set({ data: null, cells: [] })
  },

  /*
   * Outcome and review capture.
   *
   * Both write to the same saved-sites list the rest of the workspace uses, so
   * they travel with an export and survive a reload. Neither is read by
   * anything that produces a finding — this is storage for a feature that does
   * not exist yet, and keeping it inert is the point.
   */
  recordOutcome: (id, note, occurredOn) => {
    const trimmed = note.trim()
    if (!trimmed) return
    const { data, scannerId } = get()
    const coverage = data?.radar?.coverage
    const outcome: SiteOutcome = {
      id: String(Date.now()),
      note: trimmed,
      occurredOn,
      recordedAt: Date.now(),
      scanner: scannerId,
      // Captured now, from the report on screen. Re-running the scan later
      // against different data must not change what this outcome was recorded
      // against.
      findingIds: (data?.radar?.flags ?? []).map((f) => f.id),
      ...(coverage ? { coverage: { assessed: coverage.assessed,
                                   relevant: coverage.relevant } } : {}),
    }
    {
      const next = get().saved.map((s) =>
      s.id === id ? { ...s, outcomes: [...(s.outcomes ?? []), outcome] } : s)
      persistSaved(next)
      set({ saved: next })
    }
  },

  removeOutcome: (siteId, outcomeId) => {
    {
      const next = get().saved.map((s) =>
      s.id === siteId
        ? { ...s, outcomes: (s.outcomes ?? []).filter((o) => o.id !== outcomeId) }
        : s)
      persistSaved(next)
      set({ saved: next })
    }
  },

  setReview: (id, review) => {
    {
      const next = get().saved.map((s) => {
      if (s.id !== id) return s
      if (!review) {
        const { review: _dropped, ...rest } = s
        return rest
      }
      return { ...s, review: { ...review, recordedAt: Date.now() } }
    })
      persistSaved(next)
      set({ saved: next })
    }
  },

  saveAoi: (name) => {
    const { aoi, data, saved, selected, timeIndex, compareIndex } = get()
    if (!aoi) return
    const entry: SavedAoi = {
      id: String(Date.now()),
      name: name.trim() || 'Untitled site',
      geometry: aoi,
      area_ha: data?.area_ha ?? 0,
      savedAt: Date.now(),
      factors: selected,
      timeIndex,
      compareIndex,
      markers: get().markers,
    }
    const next = [entry, ...saved].slice(0, 50)
    persistSaved(next)
    set({ saved: next, projectName: entry.name })
    // Naming a site changes what the link says it is.
    get().syncUrl()
  },

  loadSaved: (id) => {
    const entry = get().saved.find((s) => s.id === id)
    if (!entry) return
    // Factors and time go in *before* the geometry, because setAoi fires the
    // fetch: setting them afterwards would request the old factor list and
    // then immediately need a second round trip to correct it.
    const patch: Partial<State> = {}
    if (entry.factors?.length) patch.selected = entry.factors.slice(0, MAX_FACTORS)
    if (typeof entry.timeIndex === 'number') patch.timeIndex = entry.timeIndex
    if (entry.compareIndex !== undefined) patch.compareIndex = entry.compareIndex
    patch.markers = entry.markers ?? []
    patch.projectName = entry.name
    set(patch)
    get().setAoi(entry.geometry, { keepProject: true })
  },

  deleteSaved: (id) => {
    const next = get().saved.filter((s) => s.id !== id)
    persistSaved(next)
    // Deleting the last one turns the home screen into a full window of
    // nothing. Hand the map back instead.
    set(next.length ? { saved: next } : { saved: next, home: false })
  },

  renameSaved: (id, name) => {
    const clean = name.trim()
    if (!clean) return
    const next = get().saved.map((s) => (s.id === id ? { ...s, name: clean } : s))
    persistSaved(next)
    set({ saved: next })
  },

  /** Overwrite a saved site with what is on screen now. Without this, refining
   *  a boundary means saving a near-duplicate and deleting the old one. */
  updateSaved: (id) => {
    const { aoi, data, saved, selected, timeIndex, compareIndex } = get()
    if (!aoi) return
    const next = saved.map((s) =>
      s.id === id
        ? { ...s, geometry: aoi, area_ha: data?.area_ha ?? s.area_ha,
            savedAt: Date.now(), factors: selected, timeIndex, compareIndex,
            markers: get().markers }
        : s,
    )
    persistSaved(next)
    set({ saved: next })
  },

  /** Merge an imported list in, keeping both sides. Returns how many arrived,
   *  so the caller can say. Ids are reissued on collision rather than
   *  overwriting: two machines both saving at the same millisecond is
   *  unlikely, but losing a site to it would be silent. */
  importSites: (sites) => {
    const { saved } = get()
    const existing = new Set(saved.map((s) => s.id))
    const arriving = sites.map((s) => (existing.has(s.id)
      ? { ...s, id: `${s.id}-${Math.random().toString(36).slice(2, 7)}` }
      : s))
    const next = [...arriving, ...saved].slice(0, 50)
    persistSaved(next)
    set({ saved: next })
    return arriving.length
  },

  // Every marker mutation syncs the URL. Markers are part of the shared
  // analysis, not a private scratch layer — a link that drops the notes off a
  // site is the failure mode this project is trying not to have.
  addMarker: (lng, lat, name) => {
    const { markers } = get()
    set({
      markers: [...markers, {
        id: `m${Date.now()}`,
        // Numbered rather than blank: an unnamed pin in a list of eight is
        // indistinguishable from the other seven, and naming can wait.
        name: name?.trim() || `Point ${markers.length + 1}`,
        lng, lat,
      }],
    })
    get().syncUrl()
  },

  renameMarker: (id, name) => {
    const clean = name.trim()
    if (!clean) return
    set({ markers: get().markers.map((m) => (m.id === id ? { ...m, name: clean } : m)) })
    get().syncUrl()
  },

  moveMarker: (id, lng, lat) => {
    set({ markers: get().markers.map((m) => (m.id === id ? { ...m, lng, lat } : m)) })
    get().syncUrl()
  },

  removeMarker: (id) => {
    set({ markers: get().markers.filter((m) => m.id !== id) })
    get().syncUrl()
  },

  toggleFactor: (id) => {
    const { selected } = get()
    const next = selected.includes(id)
      ? selected.filter((s) => s !== id)
      : selected.length >= MAX_FACTORS
        ? selected
        : [...selected, id]
    if (next === selected) return
    // Removing the last factor would leave the table with nothing to show.
    if (next.length === 0) return
    set({ selected: next })
    if (get().aoi) void get().refresh()
    get().syncUrl()
  },

  setSelected: (ids) => {
    if (!ids.length) return
    set({ selected: ids.slice(0, MAX_FACTORS) })
    if (get().aoi) void get().refresh()
    get().syncUrl()
  },

  applyTemplate: (t) => {
    set({ selected: t.factors.slice(0, MAX_FACTORS), drawMode: t.tool })
    if (get().aoi) void get().refresh()
  },

  setTimeIndex: (i) => { set({ timeIndex: i }); get().syncUrl() },
  setCompareIndex: (i) => { set({ compareIndex: i }); get().syncUrl() },
  setPlaying: (p) => set({ playing: p }),
  setTab: (t) => set({ activeTab: t }),
  // Opening one closes the other: they are two depths of the same question,
  // and stacking two dialogues leaves no obvious way back.
  openEvidence: (factor) => set({ evidenceFactor: factor, investigationId: null }),
  openInvestigation: (id) => {
    set({ investigationId: id, evidenceFactor: null })
    get().syncUrl()
  },
  closeInvestigation: () => {
    set({ investigationId: null })
    get().syncUrl()
  },
  closeEvidence: () => set({ evidenceFactor: null }),
  setBrowserOpen: (o) => set({ browserOpen: o }),
  setSidebarOpen: (o) => set({ sidebarOpen: o }),
  setSidebarSection: (s) => set({ sidebarSection: s }),
  setPanelOpen: (o) => set({ panelOpen: o }),
  setOverlayOpacity: (o) => set({ overlayOpacity: Math.max(0, Math.min(1, o)) }),
  setCursor: (c) => set({ cursor: c }),
  setView: (v) => set({ view: v }),

  // Keeps the address bar in step with state, so a copied URL always restores
  // exactly what is on screen.
  syncUrl: () => {
    const s = get()
    writeUrl({
      aoi: s.aoi,
      factors: s.selected,
      t: s.timeIndex,
      compare: s.compareIndex,
      markers: s.markers,
      name: s.projectName,
      investigation: s.investigationId,
    })
  },

  hydrateFromUrl: () => {
    const s = decodeState(location.hash)
    if (s.factors?.length) set({ selected: s.factors.slice(0, MAX_FACTORS) })
    if (s.compare !== undefined && s.compare !== null) set({ compareIndex: s.compare })
    if (s.markers?.length) set({ markers: s.markers })
    if (s.name) set({ projectName: s.name })
    // The workspace opens once the report arrives — the id alone means
    // nothing until the recipient's own assessment has run and either raises
    // that investigation or does not.
    if (s.investigation) set({ investigationId: s.investigation })
    // Geometry last: setAoi fires the fetch, and it clears projectName unless
    // told to keep it — so the name has to be in place before it runs, and the
    // restore has to declare itself a restore.
    if (s.aoi) get().setAoi(s.aoi, { skipHistory: true, keepProject: true })
  },

  refresh: async () => {
    if (!get().aoi || get().selected.length === 0) return

    // Coalesce a burst of changes into one request. Loading goes up straight
    // away so the interface answers the click, even though nothing has left
    // for the network yet.
    set({ loading: true, error: null })
    const generation = ++refreshGeneration
    await new Promise<void>((resolve) => setTimeout(resolve, REFRESH_DEBOUNCE_MS))
    // A later call arrived during the window and will do the work.
    if (generation !== refreshGeneration) return

    // Read after the wait, not before: the whole point of the window is that
    // the selection may have changed inside it.
    const { aoi, selected } = get()
    if (!aoi || selected.length === 0) {
      set({ loading: false })
      return
    }

    // Redrawing during the request itself still needs the abort: the debounce
    // only covers changes closer together than the window.
    inflight?.abort()
    const ctrl = new AbortController()
    inflight = ctrl

    try {
      const [data, cells] = await Promise.all([
        // The active scanner goes with the request. Without it the backend
        // falls back to its default and assesses a habitat site with land's
        // rules — see api.ts.
        fetchSeries(aoi, selected, get().scannerId, ctrl.signal),
        fetchCells(aoi, get().scannerId, ctrl.signal),
      ])
      if (ctrl.signal.aborted) return
      set({ data, cells: cells.cells, loading: false, timeIndex: settleTime(data, selected, get().timeIndex) })
    } catch (e: any) {
      if (e?.name === 'AbortError') return
      set({ error: e?.message ?? 'Something went wrong', loading: false, data: null })
    }
  },
}))

/** Factors grouped for the browser, preserving catalogue order. */
export function groupFactors(factors: Factor[]): Record<string, Factor[]> {
  const out: Record<string, Factor[]> = {}
  for (const f of factors) (out[f.group] ??= []).push(f)
  return out
}
