/**
 * Backgrounds for the draw page. Context only: the PDF sheet uses its own OS
 * basemap (OS_API_KEY), so nothing here reaches a client.
 *
 * The Esri layers are the same tiles ArcGIS Online uses. Esri's terms allow
 * them in a tool like this with attribution shown; check them before using
 * the imagery in anything you send out.
 */

export interface Basemap {
  id: string
  name: string
  /** Raster tile layers, bottom first. A hybrid stacks labels over imagery. */
  tiles: string[]
  attribution: string
  maxzoom: number
  /** Dimmed for the dark interface; imagery stays at full strength. */
  dim?: boolean
}

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services'
const ESRI_ATTR = 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'

export const BASEMAPS: Basemap[] = [
  {
    id: 'satellite', name: 'Satellite',
    tiles: [`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`],
    attribution: ESRI_ATTR, maxzoom: 19,
  },
  {
    id: 'hybrid', name: 'Satellite + labels',
    tiles: [
      `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
      `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`,
      `${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`,
    ],
    attribution: ESRI_ATTR, maxzoom: 19,
  },
  {
    id: 'topo', name: 'Topographic',
    tiles: [`${ESRI}/World_Topo_Map/MapServer/tile/{z}/{y}/{x}`],
    attribution: 'Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors, and the GIS community',
    maxzoom: 19,
  },
  {
    id: 'streets', name: 'OpenStreetMap',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors', maxzoom: 19,
  },
  {
    id: 'grey', name: 'Light grey',
    tiles: [`${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`],
    attribution: 'Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors', maxzoom: 16,
  },
]

export const DEFAULT_BASEMAP = 'satellite'
