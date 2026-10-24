// Shapes returned by sheet/api.py. If one moves, the other must.

export type Status = 'present' | 'none_found' | 'not_assessed'

export interface LayerStyle {
  fill: string          // hex, or "none"
  edge: string
  alpha: number
  hatched: boolean
}

export interface Layer {
  id: string
  name: string
  group: string
  /** Search radius from the red line in metres. 0 = the red line only. */
  search_m: number
  publisher: string
  /** False for layers reported in the findings but not drawn (risk zones, ALC). */
  on_map: boolean
  geom: 'polygon' | 'line' | 'point'
  style: LayerStyle
}

export interface Info {
  /** True when the backend reads fixtures. Everything it returns is fiction. */
  test_data: boolean
  max_ha: number
  groups: string[]
}

export interface Finding {
  layer: string
  name: string
  group: string
  status: Status
  search_m: number
  on_site: boolean
  /** The same sentence the PDF prints. */
  summary: string
  /** Why the layer was not assessed. Empty otherwise. */
  error: string
}

export interface SheetRecord {
  job: string
  title: string
  client_ref: string
  made_at: string
  area_ha: number
  scale: number
  /** True when the OS basemap loaded (needs OS_API_KEY). */
  basemap: boolean
  test_data: boolean
  counts: Record<Status, number>
  findings: Finding[]
  urls: { pdf: string; gpkg: string; json: string }
  /** Features each present layer returned, WGS84, keyed by layer id. */
  map: Record<string, GeoJSON.FeatureCollection>
}

export type DrawMode = 'rect' | 'circle' | 'freehand' | null
