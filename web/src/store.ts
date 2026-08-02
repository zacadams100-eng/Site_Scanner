import { create } from 'zustand'
import type { Catalog, Cell, DrawMode, Factor, SeriesResponse } from './types'
import { fetchCells, fetchSeries } from './api'
import { decodeState, writeUrl, type Template } from './lib/permalink'

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
const SAVED_KEY = 'site-scanner.saved-aois'

export interface SavedAoi {
  id: string
  name: string
  geometry: GeoJSON.Polygon
  area_ha: number
  savedAt: number
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
  saveAoi: (name: string) => void
  loadSaved: (id: string) => void
  deleteSaved: (id: string) => void
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

export const useStore = create<State>((set, get) => ({
  catalog: null,
  catalogError: null,
  isMock: false,
  aoi: null,
  drawMode: null,
  cells: [],
  past: [],
  future: [],
  saved: loadSaved(),
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

  saveAoi: (name) => {
    const { aoi, data, saved } = get()
    if (!aoi) return
    const entry: SavedAoi = {
      id: String(Date.now()),
      name: name.trim() || 'Untitled site',
      geometry: aoi,
      area_ha: data?.area_ha ?? 0,
      savedAt: Date.now(),
    }
    const next = [entry, ...saved].slice(0, 50)
    persistSaved(next)
    set({ saved: next })
  },

  loadSaved: (id) => {
    const entry = get().saved.find((s) => s.id === id)
    if (entry) get().setAoi(entry.geometry)
  },

  deleteSaved: (id) => {
    const next = get().saved.filter((s) => s.id !== id)
    persistSaved(next)
    set({ saved: next })
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
    set({ selected: t.factors.slice(0, MAX_FACTORS), templatesOpen: false, drawMode: t.tool })
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
      set({ data, cells: cells.cells, loading: false })
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
