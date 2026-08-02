import { create } from 'zustand'
import type { Catalog, Cell, DrawMode, Factor, SeriesResponse } from './types'
import { fetchCells, fetchSeries } from './api'

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

interface State {
  catalog: Catalog | null
  catalogError: string | null
  isMock: boolean

  aoi: GeoJSON.Polygon | null
  drawMode: DrawMode
  cells: Cell[]

  selected: string[]
  data: SeriesResponse | null
  loading: boolean
  error: string | null

  timeIndex: number
  playing: boolean

  activeTab: 'table' | 'charts' | 'sources'
  browserOpen: boolean

  setCatalog: (c: Catalog) => void
  setCatalogError: (e: string) => void
  setMock: (m: boolean) => void
  setDrawMode: (m: DrawMode) => void
  setAoi: (g: GeoJSON.Polygon | null) => void
  toggleFactor: (id: string) => void
  setSelected: (ids: string[]) => void
  setTimeIndex: (i: number) => void
  setPlaying: (p: boolean) => void
  setTab: (t: 'table' | 'charts' | 'sources') => void
  setBrowserOpen: (o: boolean) => void
  refresh: () => Promise<void>
}

let inflight: AbortController | null = null

export const useStore = create<State>((set, get) => ({
  catalog: null,
  catalogError: null,
  isMock: false,
  aoi: null,
  drawMode: null,
  cells: [],
  selected: DEFAULT_FACTORS,
  data: null,
  loading: false,
  error: null,
  timeIndex: 0,
  playing: false,
  activeTab: 'table',
  browserOpen: false,

  setCatalog: (c) =>
    set({
      catalog: c,
      // Land on the most recent step: users overwhelmingly want "now" first,
      // then scrub backwards to see how it got there.
      timeIndex: Math.max(0, c.time.steps.length - 1),
    }),
  setCatalogError: (e) => set({ catalogError: e }),
  setMock: (m) => set({ isMock: m }),
  setDrawMode: (m) => set({ drawMode: m }),

  setAoi: (g) => {
    set({ aoi: g, drawMode: null })
    if (g) void get().refresh()
    else set({ data: null, cells: [], error: null })
  },

  toggleFactor: (id) => {
    const { selected } = get()
    // 12 is a soft ceiling: past that the table stops being readable and the
    // request gets slow. The browser surfaces this rather than silently
    // dropping the click.
    const next = selected.includes(id)
      ? selected.filter((s) => s !== id)
      : selected.length >= 12
        ? selected
        : [...selected, id]
    if (next === selected) return
    set({ selected: next })
    if (get().aoi) void get().refresh()
  },

  setSelected: (ids) => {
    set({ selected: ids })
    if (get().aoi) void get().refresh()
  },

  setTimeIndex: (i) => set({ timeIndex: i }),
  setPlaying: (p) => set({ playing: p }),
  setTab: (t) => set({ activeTab: t }),
  setBrowserOpen: (o) => set({ browserOpen: o }),

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
