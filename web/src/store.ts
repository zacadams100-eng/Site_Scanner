import { create } from 'zustand'
import type { DrawMode, Info, Layer, SheetRecord } from './types'
import { fetchInfo, fetchLayers, makeSheet } from './api'
import { BASEMAPS, DEFAULT_BASEMAP } from './lib/basemaps'

/**
 * One rule matters more than the rest: a sheet belongs to the red line it was
 * made for. Redrawing, undoing or clearing the red line drops the sheet, so
 * the panel can never show findings for a shape that is no longer on the map.
 */

interface State {
  info: Info | null
  layers: Layer[]
  apiError: string | null

  redLine: GeoJSON.Polygon | null
  drawMode: DrawMode
  // Undo/redo over drawn shapes.
  past: (GeoJSON.Polygon | null)[]
  future: (GeoJSON.Polygon | null)[]

  title: string
  clientRef: string
  sheet: SheetRecord | null
  making: boolean
  error: string | null
  /** Layer ids hidden on the map. Findings stay in the panel either way. */
  hidden: string[]
  basemap: string

  load: () => Promise<void>
  setDrawMode: (m: DrawMode) => void
  setRedLine: (g: GeoJSON.Polygon | null) => void
  undo: () => void
  redo: () => void
  setTitle: (t: string) => void
  setClientRef: (r: string) => void
  make: () => Promise<void>
  toggleHidden: (id: string) => void
  setBasemap: (id: string) => void
}

const BASEMAP_KEY = 'contour.basemap'

function savedBasemap(): string {
  try {
    const id = localStorage.getItem(BASEMAP_KEY)
    if (id && BASEMAPS.some((b) => b.id === id)) return id
  } catch {
    /* storage blocked — fall back to the default */
  }
  return DEFAULT_BASEMAP
}

let inflight: AbortController | null = null

function dropSheet() {
  inflight?.abort()
  return { sheet: null, making: false, error: null }
}

export const useStore = create<State>((set, get) => ({
  info: null,
  layers: [],
  apiError: null,
  redLine: null,
  drawMode: null,
  past: [],
  future: [],
  title: '',
  clientRef: '',
  sheet: null,
  making: false,
  error: null,
  hidden: [],
  basemap: savedBasemap(),

  load: async () => {
    try {
      const [info, layers] = await Promise.all([fetchInfo(), fetchLayers()])
      set({ info, layers, apiError: null })
    } catch (e: any) {
      set({ apiError: e?.message ?? 'Could not reach the API' })
    }
  },

  setDrawMode: (m) => set({ drawMode: m }),

  setRedLine: (g) => {
    const { redLine, past } = get()
    set({ redLine: g, drawMode: null, past: [...past, redLine].slice(-40), future: [], ...dropSheet() })
  },

  undo: () => {
    const { past, redLine, future } = get()
    if (!past.length) return
    set({ past: past.slice(0, -1), future: [redLine, ...future].slice(0, 40),
          redLine: past[past.length - 1], ...dropSheet() })
  },

  redo: () => {
    const { future, redLine, past } = get()
    if (!future.length) return
    set({ future: future.slice(1), past: [...past, redLine].slice(-40), redLine: future[0], ...dropSheet() })
  },

  setTitle: (t) => set({ title: t }),
  setClientRef: (r) => set({ clientRef: r }),

  make: async () => {
    const { redLine, title, clientRef } = get()
    if (!redLine || !title.trim() || !clientRef.trim()) return
    inflight?.abort()
    const ctrl = new AbortController()
    inflight = ctrl
    set({ making: true, error: null, sheet: null })
    try {
      const sheet = await makeSheet(redLine, title.trim(), clientRef.trim(), ctrl.signal)
      if (!ctrl.signal.aborted) set({ sheet, making: false })
    } catch (e: any) {
      if (e?.name === 'AbortError') return
      set({ error: e?.message ?? 'Something went wrong', making: false })
    }
  },

  toggleHidden: (id) => {
    const { hidden } = get()
    set({ hidden: hidden.includes(id) ? hidden.filter((h) => h !== id) : [...hidden, id] })
  },

  setBasemap: (id) => {
    try { localStorage.setItem(BASEMAP_KEY, id) } catch { /* convenience only */ }
    set({ basemap: id })
  },
}))
