import { create } from 'zustand'
import type { Catalog, Cell, DrawMode, Factor, SeriesResponse } from './types'
import { fetchCells, fetchSeries } from './api'
import { decodeState, writeUrl, type Template } from './lib/permalink'
import {
  copyName, loadProjects, persistProjects, sortProjects, type Project,
} from './lib/projects'

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

  projects: Project[]
  /**
   * The project currently open, if any. This is what makes Save mean "update"
   * rather than "add another": without it, saving twice leaves two cards in
   * the gallery that look identical and diverge from then on.
   */
  currentProjectId: string | null
  galleryOpen: boolean

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

  activeTab: 'table' | 'charts' | 'sources'
  browserOpen: boolean
  templatesOpen: boolean

  setCatalog: (c: Catalog) => void
  setCatalogError: (e: string) => void
  setMock: (m: boolean) => void
  setDrawMode: (m: DrawMode) => void
  setAoi: (g: GeoJSON.Polygon | null, opts?: { skipHistory?: boolean }) => void
  undo: () => void
  redo: () => void
  saveProject: (name?: string) => void
  openProject: (id: string) => void
  renameProject: (id: string, name: string) => void
  duplicateProject: (id: string) => void
  deleteProject: (id: string) => void
  newProject: () => void
  setGalleryOpen: (o: boolean) => void
  toggleFactor: (id: string) => void
  setSelected: (ids: string[]) => void
  applyTemplate: (t: Template) => void
  setTimeIndex: (i: number) => void
  setCompareIndex: (i: number | null) => void
  setPlaying: (p: boolean) => void
  setTab: (t: 'table' | 'charts' | 'sources') => void
  setBrowserOpen: (o: boolean) => void
  setTemplatesOpen: (o: boolean) => void
  refresh: () => Promise<void>
  hydrateFromUrl: () => void
  syncUrl: () => void
}

let inflight: AbortController | null = null

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

/**
 * Whether the app was opened on a shared link.
 *
 * A permalink carries a specific view and is usually someone else's — landing
 * on a gallery of *your* projects instead would be the wrong answer to
 * "someone sent me this". Read once at module load, before any hash rewriting
 * happens.
 */
const OPENED_WITH_LINK = !!decodeState(location.hash).aoi

const INITIAL_PROJECTS = loadProjects(DEFAULT_FACTORS)

export const useStore = create<State>((set, get) => ({
  catalog: null,
  catalogError: null,
  isMock: false,
  aoi: null,
  drawMode: null,
  cells: [],
  past: [],
  future: [],
  projects: INITIAL_PROJECTS,
  currentProjectId: null,
  // Open on the gallery when there is something to choose between, exactly as
  // Procreate does. A first-run user with nothing saved gets the canvas
  // instead — an empty gallery is a door into an empty room.
  galleryOpen: !OPENED_WITH_LINK && INITIAL_PROJECTS.length > 0,
  selected: DEFAULT_FACTORS,
  data: null,
  loading: false,
  error: null,
  timeIndex: 0,
  playing: false,
  compareIndex: null,
  activeTab: 'table',
  browserOpen: false,
  templatesOpen: false,

  setCatalog: (c) => {
    // Land on the most recent step: users overwhelmingly want "now" first,
    // then scrub backwards to see how it got there. A URL overrides this.
    const fromUrl = decodeState(location.hash)
    set({
      catalog: c,
      timeIndex: fromUrl.t ?? Math.max(0, c.time.steps.length - 1),
    })
    get().hydrateFromUrl()
  },
  setCatalogError: (e) => set({ catalogError: e }),
  setMock: (m) => set({ isMock: m }),
  setDrawMode: (m) => set({ drawMode: m }),

  setAoi: (g, opts) => {
    const { aoi, past } = get()
    set({
      aoi: g,
      drawMode: null,
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

  /**
   * Save the working state. Updates the open project when there is one, and
   * only creates a card when there is not — so a session of repeated saves
   * leaves one project, not twelve.
   */
  saveProject: (name) => {
    const { aoi, data, projects, currentProjectId, selected, timeIndex } = get()
    if (!aoi) return
    const now = Date.now()
    const existing = currentProjectId
      ? projects.find((p) => p.id === currentProjectId)
      : undefined

    const entry: Project = {
      id: existing?.id ?? `p${now}`,
      name: name?.trim() || existing?.name || 'Untitled site',
      geometry: aoi,
      area_ha: data?.area_ha ?? existing?.area_ha ?? 0,
      factors: selected,
      timeIndex,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
    }

    const next = sortProjects([entry, ...projects.filter((p) => p.id !== entry.id)])
    persistProjects(next)
    set({ projects: next, currentProjectId: entry.id })
  },

  /**
   * Restore a whole project, not just its outline: factors first so the
   * refresh `setAoi` triggers already asks for the right columns, then the
   * time position once the data lands.
   */
  openProject: (id) => {
    const entry = get().projects.find((p) => p.id === id)
    if (!entry) return
    set({
      selected: entry.factors.slice(0, MAX_FACTORS),
      currentProjectId: entry.id,
      galleryOpen: false,
      compareIndex: null,
      // A project is a starting point, not a step in the current edit history.
      past: [],
      future: [],
    })
    if (entry.timeIndex !== null) set({ timeIndex: entry.timeIndex })
    get().setAoi(entry.geometry, { skipHistory: true })
  },

  renameProject: (id, name) => {
    const clean = name.trim()
    if (!clean) return
    const next = get().projects.map((p) =>
      p.id === id ? { ...p, name: clean, updatedAt: Date.now() } : p)
    persistProjects(next)
    set({ projects: sortProjects(next) })
  },

  duplicateProject: (id) => {
    const { projects } = get()
    const src = projects.find((p) => p.id === id)
    if (!src) return
    const now = Date.now()
    const copy: Project = {
      ...src,
      id: `p${now}`,
      name: copyName(src.name, projects.map((p) => p.name)),
      createdAt: now,
      updatedAt: now,
    }
    const next = sortProjects([copy, ...projects])
    persistProjects(next)
    set({ projects: next })
  },

  deleteProject: (id) => {
    const next = get().projects.filter((p) => p.id !== id)
    persistProjects(next)
    set({
      projects: next,
      // Deleting the open project leaves the canvas as-is but unhitched, so
      // the next Save creates a fresh card rather than resurrecting the one
      // just deleted.
      currentProjectId: get().currentProjectId === id ? null : get().currentProjectId,
    })
  },

  /** A blank canvas: no shape, no project, default factors. */
  newProject: () => {
    set({
      currentProjectId: null,
      galleryOpen: false,
      selected: DEFAULT_FACTORS,
      compareIndex: null,
      past: [],
      future: [],
    })
    get().setAoi(null, { skipHistory: true })
  },

  setGalleryOpen: (o) => set({ galleryOpen: o }),

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
    set({
      selected: t.factors.slice(0, MAX_FACTORS),
      templatesOpen: false,
      drawMode: t.tool,
      // Templates are reachable from the gallery, where picking one is a way
      // of starting a new project — so it has to put you on the canvas with
      // the tool already in hand.
      galleryOpen: false,
    })
    if (get().aoi) void get().refresh()
  },

  setTimeIndex: (i) => { set({ timeIndex: i }); get().syncUrl() },
  setCompareIndex: (i) => { set({ compareIndex: i }); get().syncUrl() },
  setPlaying: (p) => set({ playing: p }),
  setTab: (t) => set({ activeTab: t }),
  setBrowserOpen: (o) => set({ browserOpen: o }),
  setTemplatesOpen: (o) => set({ templatesOpen: o }),

  // Keeps the address bar in step with state, so a copied URL always restores
  // exactly what is on screen.
  syncUrl: () => {
    const s = get()
    writeUrl({ aoi: s.aoi, factors: s.selected, t: s.timeIndex, compare: s.compareIndex })
  },

  hydrateFromUrl: () => {
    const s = decodeState(location.hash)
    if (s.factors?.length) set({ selected: s.factors.slice(0, MAX_FACTORS) })
    if (s.compare !== undefined && s.compare !== null) set({ compareIndex: s.compare })
    if (s.aoi) get().setAoi(s.aoi, { skipHistory: true })
  },

  refresh: async () => {
    const { aoi, selected } = get()
    if (!aoi || selected.length === 0) return

    // A user redrawing quickly, or toggling three factors in a row, should not
    // queue three round trips whose answers arrive out of order.
    inflight?.abort()
    const ctrl = new AbortController()
    inflight = ctrl

    set({ loading: true, error: null })
    try {
      const [data, cells] = await Promise.all([
        fetchSeries(aoi, selected, ctrl.signal),
        fetchCells(aoi, ctrl.signal),
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
