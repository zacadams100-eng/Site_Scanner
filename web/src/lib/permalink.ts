import type { DrawMode, Marker } from '../types'

/**
 * URL state.
 *
 * The single biggest failure of GEE workflows is irreproducibility — a
 * colleague asks "how did you get that number?" and the answer is a script
 * nobody can run. A URL that restores exact state is the cheapest credibility
 * feature available, and it is also the primary organic growth channel.
 *
 * Encoded in the hash rather than the query string so that restoring state
 * never round-trips to a server.
 *
 * **Every field of `UrlState` must survive a round trip.** Not "most of it",
 * and not "the parts that are cheap to encode" — a link that restores four
 * fifths of an analysis is worse than one that restores none, because the
 * recipient cannot see which fifth is missing and reads the remainder as the
 * whole. `URL_STATE_KEYS` below names the fields, and a test walks it and
 * fails on any that does not come back; adding a field to this interface
 * without teaching `encodeState`/`decodeState` about it breaks that test on
 * purpose.
 */

export interface UrlState {
  aoi: GeoJSON.Polygon | null
  factors: string[]
  t: number
  compare: number | null
  /** Annotated points. Saved with a workspace since markers existed, but until
   *  now dropped from the URL — so sharing an annotated site sent the shape
   *  and silently discarded every note on it. */
  markers: Marker[]
  /** The site's name, when it has one. What the recipient sees in the top bar,
   *  and the difference between opening "Manor Farm, parcel 3" and opening an
   *  unnamed rectangle. */
  name: string | null
}

/** The field list the completeness test walks. Kept beside the interface so
 *  the two are edited in the same glance. */
export const URL_STATE_KEYS: (keyof UrlState)[] =
  ['aoi', 'factors', 't', 'compare', 'markers', 'name']

/** Polygons are the bulky part, so coordinates are quantised to ~1 m and
 *  delta-encoded before base64. A 60-vertex freehand shape fits in a URL that
 *  still pastes into Slack without wrapping. */
function encodeRing(ring: number[][]): string {
  const q = (v: number) => Math.round(v * 1e5)
  let px = 0
  let py = 0
  const parts: string[] = []
  for (const [lng, lat] of ring) {
    const x = q(lng)
    const y = q(lat)
    parts.push(`${x - px}.${y - py}`)
    px = x
    py = y
  }
  return parts.join('_')
}

function decodeRing(s: string): number[][] {
  let px = 0
  let py = 0
  const out: number[][] = []
  for (const part of s.split('_')) {
    const i = part.indexOf('.', part[0] === '-' ? 1 : 0)
    if (i < 0) continue
    px += Number(part.slice(0, i))
    py += Number(part.slice(i + 1))
    out.push([px / 1e5, py / 1e5])
  }
  return out
}

/**
 * Markers, as `lng,lat,name;lng,lat,name`.
 *
 * The separators are `;` and `,` specifically because `encodeURIComponent`
 * escapes both, so a marker called "north gate; by the oak" cannot punch its
 * way out of its own field. The obvious-looking choices — `~`, `*`, `!` — are
 * all left untouched by `encodeURIComponent` and would have worked in testing
 * and failed on the first user who typed one.
 *
 * Coordinates are quantised to ~1 m, matching the ring encoding. A marker is a
 * dropped pin, not a survey control point.
 */
function encodeMarkers(markers: Marker[]): string {
  return markers
    .map((m) => [
      Math.round(m.lng * 1e5),
      Math.round(m.lat * 1e5),
      encodeURIComponent(m.name),
    ].join(','))
    .join(';')
}

function decodeMarkers(s: string): Marker[] {
  const out: Marker[] = []
  for (const part of s.split(';')) {
    if (!part) continue
    const [x, y, ...rest] = part.split(',')
    const lng = Number(x)
    const lat = Number(y)
    // A truncated or mangled marker is dropped rather than placed at 0°N 0°E,
    // which is in the Atlantic and would read as a real annotation.
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue
    let name = 'Point'
    try {
      name = decodeURIComponent(rest.join(',')) || 'Point'
    } catch {
      // A hand-edited URL can carry a `%` that is not an escape sequence.
      name = rest.join(',') || 'Point'
    }
    // Ids are reissued by position rather than carried. They are local handles
    // for React keys and edit operations, not content — nothing outside this
    // browser has ever seen one, so spending URL length on them buys nothing.
    out.push({ id: `m${out.length}`, name, lng: lng / 1e5, lat: lat / 1e5 })
  }
  return out
}

export function encodeState(s: UrlState): string {
  const parts: string[] = []
  if (s.aoi) parts.push('g=' + encodeRing(s.aoi.coordinates[0] as number[][]))
  if (s.factors.length) parts.push('f=' + s.factors.join('.'))
  parts.push('t=' + s.t)
  if (s.compare !== null) parts.push('c=' + s.compare)
  if (s.markers.length) parts.push('m=' + encodeMarkers(s.markers))
  if (s.name) parts.push('n=' + encodeURIComponent(s.name))
  return parts.join('&')
}

export function decodeState(hash: string): Partial<UrlState> {
  const raw = hash.replace(/^#/, '')
  if (!raw) return {}
  const out: Partial<UrlState> = {}
  for (const kv of raw.split('&')) {
    const i = kv.indexOf('=')
    if (i < 0) continue
    const k = kv.slice(0, i)
    const v = kv.slice(i + 1)
    if (k === 'g') {
      const ring = decodeRing(v)
      // A polygon needs at least a triangle plus its closing vertex.
      if (ring.length >= 3) {
        const closed = ring[0][0] === ring[ring.length - 1][0] &&
          ring[0][1] === ring[ring.length - 1][1]
        out.aoi = {
          type: 'Polygon',
          coordinates: [closed ? ring : [...ring, ring[0]]],
        }
      }
    } else if (k === 'f') out.factors = v.split('.').filter(Boolean)
    else if (k === 't') out.t = Number(v)
    else if (k === 'c') out.compare = Number(v)
    else if (k === 'm') out.markers = decodeMarkers(v)
    else if (k === 'n') {
      try {
        out.name = decodeURIComponent(v) || null
      } catch {
        out.name = v || null
      }
    }
  }
  return out
}

export function writeUrl(s: UrlState): void {
  const encoded = encodeState(s)
  // replaceState, not pushState: scrubbing the timeline must not fill the
  // browser's back stack with 180 entries.
  history.replaceState(null, '', '#' + encoded)
}

export function shareUrl(s: UrlState): string {
  return `${location.origin}${location.pathname}#${encodeState(s)}`
}

/**
 * Guided starting points, grouped by the profession that asks for them.
 *
 * The target user knows their own trade but not this interface, and a
 * catalogue of 260 factors is a filing cabinet until something tells you
 * which drawer is yours. A template is a worked example that produces a real
 * answer on the first visit — and, read as a list, it is also the honest
 * statement of who this tool is for.
 *
 * Each one picks factors that genuinely belong together in that trade's
 * screen. None of them draws the area for you; the shape is still the user's.
 *
 * ## Every name and blurb states what Contour investigates, never what to decide
 *
 * This list is the first thing a new user reads, so it is the product's
 * positioning whether or not anyone intended it that way — and it used to
 * open with *"Development appraisal — is this site worth pursuing?"*. That is
 * a suitability question, which is the one question Contour exists not to
 * answer: it promised a verdict on the first screen and made the tool
 * indistinguishable from a land-opportunity platform.
 *
 * The rule now: a template names a **body of evidence**, not a decision and
 * not an outcome. "Solar site evidence", never "Solar farm". "Recorded
 * irradiance, slope, shading", never "Would an array work here". The factors
 * behind each one are unchanged — the job being promised is what changed.
 *
 * Also gone: "appraisal" (a judgement of worth), "quality" (a judgement of the
 * place), and blurbs that predicted cost, yield or value, none of which
 * Contour measures or can support.
 */
export interface Template {
  id: string
  name: string
  blurb: string
  sector: string
  factors: string[]
  tool: DrawMode
}

export const TEMPLATES: Template[] = [
  // --- Property & development -------------------------------------------
  {
    id: 'site-appraisal',
    name: 'Development evidence',
    blurb: 'What evidence should be considered before pursuing this site: value context, constraints and consent history.',
    sector: 'Property & development',
    factors: ['median_sale_price', 'land_value_residential', 'planning_approval_rate',
              'flood_zone3_pct', 'green_belt_pct', 'developable_area'],
    tool: 'rect',
  },
  {
    id: 'planning-risk',
    name: 'Planning constraints',
    blurb: 'What designations and consent history are recorded against this land.',
    sector: 'Property & development',
    factors: ['conservation_area_pct', 'listed_building_density', 'article4_pct',
              'tpo_density', 'scheduled_monument_pct', 'planning_decision_days'],
    tool: 'freehand',
  },
  {
    id: 'residential-market',
    name: 'Residential market evidence',
    blurb: 'What the local market record shows: prices, rents, turnover and affordability.',
    sector: 'Property & development',
    factors: ['median_sale_price', 'price_growth_5yr', 'sales_velocity',
              'rental_median', 'gross_yield', 'affordability_ratio'],
    tool: 'rect',
  },
  {
    id: 'ground-conditions',
    name: 'Ground conditions evidence',
    blurb: 'What is recorded beneath this site, and what that would prompt you to investigate.',
    sector: 'Property & development',
    factors: ['subsidence_risk', 'shrink_swell_score', 'coal_mining_pct',
              'historic_landfill_pct', 'radon_potential', 'earthworks_volume'],
    tool: 'rect',
  },
  {
    id: 'retrofit',
    name: 'Retrofit and EPC evidence',
    blurb: 'What the recorded energy performance of the local stock is.',
    sector: 'Property & development',
    factors: ['epc_mean_sap', 'epc_below_c_share', 'epc_potential_uplift',
              'retrofit_cost_index', 'heat_demand_density', 'heat_pump_share'],
    tool: 'rect',
  },

  // --- Infrastructure & energy ------------------------------------------
  {
    id: 'grid-connection',
    name: 'Grid connection evidence',
    blurb: 'What is recorded about capacity, distance and connection constraints here.',
    sector: 'Infrastructure & energy',
    factors: ['grid_headroom', 'distance_substation', 'grid_connection_cost',
              'curtailment_risk', 'slope_mean', 'distance_a_road'],
    tool: 'rect',
  },
  {
    id: 'solar-farm',
    name: 'Solar site evidence',
    blurb: 'Recorded irradiance, slope, shading and land classification.',
    sector: 'Infrastructure & energy',
    factors: ['solar_ghi', 'solar_farm_suitability', 'slope_mean',
              'shading_horizon_loss', 'grid_headroom', 'bmv_land_pct'],
    tool: 'circle',
  },
  {
    id: 'wind-site',
    name: 'Wind resource',
    blurb: 'Recorded wind speed, capacity factor and ground exposure.',
    sector: 'Infrastructure & energy',
    factors: ['wind_speed_100m', 'wind_capacity_factor', 'wind_power_density',
              'elevation_mean', 'distance_substation', 'aonb_pct'],
    tool: 'circle',
  },
  {
    id: 'battery-storage',
    name: 'Grid & storage evidence',
    blurb: 'Recorded gradient, grid headroom, flood exposure and access.',
    sector: 'Infrastructure & energy',
    factors: ['battery_site_suitability', 'grid_headroom', 'slope_mean',
              'flood_zone3_pct', 'distance_substation', 'hgv_access_class'],
    tool: 'rect',
  },
  {
    id: 'digital-infra',
    name: 'Digital infrastructure evidence',
    blurb: 'What connectivity is recorded in this area.',
    sector: 'Infrastructure & energy',
    factors: ['broadband_gigabit_pct', 'broadband_median_speed', 'mobile_5g_coverage',
              'broadband_notspot_pct', 'population_density', 'households'],
    tool: 'rect',
  },

  // --- Land & rural ------------------------------------------------------
  {
    id: 'farm-appraisal',
    name: 'Farm land evidence',
    blurb: 'What is recorded about growing conditions and workable days.',
    sector: 'Land & rural',
    factors: ['alc_grade', 'bmv_land_pct', 'yield_potential_wheat',
              'workable_days', 'soil_organic_carbon', 'field_size_mean'],
    tool: 'freehand',
  },
  {
    id: 'crop-season',
    name: 'Crop performance',
    blurb: 'How this field has measured, season by season.',
    sector: 'Land & rural',
    factors: ['ndvi', 'soil_moisture', 'growing_degree_days',
              'crop_stress_days', 'irrigation_demand', 'precip_total'],
    tool: 'freehand',
  },
  {
    id: 'bng',
    name: 'Biodiversity baseline evidence',
    blurb: 'What habitat and cover are recorded here now.',
    sector: 'Land & rural',
    factors: ['bng_units_available', 'bng_uplift_potential', 'lc_dominant',
              'priority_habitat_pct', 'ancient_woodland_pct', 'lc_diversity'],
    tool: 'freehand',
  },
  {
    id: 'woodland-creation',
    name: 'Woodland creation evidence',
    blurb: 'What is recorded about this ground, and what to establish before planting.',
    sector: 'Land & rural',
    factors: ['woodland_creation_suitability', 'canopy_cover_pct', 'sequestration_rate',
              'bmv_land_pct', 'soil_ph', 'windthrow_risk'],
    tool: 'freehand',
  },
  {
    id: 'vegetation',
    name: 'Vegetation change',
    blurb: 'How green cover has measured across fifteen years.',
    sector: 'Land & rural',
    factors: ['ndvi', 'lc_tree_pct', 'lc_grass_pct', 'precip_total'],
    tool: 'freehand',
  },

  // --- Risk & insurance --------------------------------------------------
  {
    id: 'flood',
    name: 'Flood exposure evidence',
    blurb: 'What flood designations and water observations are recorded, and how they have changed.',
    sector: 'Risk & insurance',
    factors: ['flood_zone3_pct', 'hand', 'water_occurrence', 'max_daily_precip'],
    tool: 'rect',
  },
  {
    id: 'peril-screen',
    name: 'Multi-peril evidence',
    blurb: 'Flood, subsidence and wind evidence in one pass.',
    sector: 'Risk & insurance',
    factors: ['insurance_peril_score', 'flood_zone3_pct', 'shrink_swell_score',
              'storm_gust_50yr', 'ground_risk_score', 'coal_mining_pct'],
    tool: 'rect',
  },
  {
    id: 'contamination',
    name: 'Contamination evidence',
    blurb: 'What was recorded here before, and what that would prompt you to investigate.',
    sector: 'Risk & insurance',
    factors: ['historic_landfill_pct', 'landfill_distance', 'contamination_flag',
              'built_change_rate', 'lc_change_rate', 'sar_coherence'],
    tool: 'rect',
  },

  // --- Siting & operations -----------------------------------------------
  {
    id: 'logistics',
    name: 'Logistics access evidence',
    blurb: 'Recorded road access, and who lives within reach.',
    sector: 'Siting & operations',
    factors: ['warehouse_suitability', 'distance_motorway_junction', 'hgv_access_class',
              'drive_time_pop_30', 'labour_pool_30', 'aadt_nearest'],
    tool: 'rect',
  },
  {
    id: 'retail-siting',
    name: 'Retail catchment evidence',
    blurb: 'Recorded population, earnings and access nearby.',
    sector: 'Siting & operations',
    factors: ['drive_time_pop_30', 'retail_catchment_spend', 'earnings_median',
              'transit_access_score', 'aadt_nearest', 'walk_score'],
    tool: 'circle',
  },
  {
    id: 'data-centre',
    name: 'Data centre evidence',
    blurb: 'Recorded power, water, fibre and flood exposure.',
    sector: 'Siting & operations',
    factors: ['data_centre_suitability', 'grid_headroom', 'water_stress_class',
              'broadband_gigabit_pct', 'flood_zone3_pct', 'slope_mean'],
    tool: 'rect',
  },
  {
    id: 'residential-quality',
    name: 'Neighbourhood evidence',
    blurb: 'What is recorded locally: schools, crime, green space and access.',
    sector: 'Siting & operations',
    factors: ['school_good_pct', 'crime_rate', 'greenspace_access',
              'transit_access_score', 'imd_score', 'gp_within_2km'],
    tool: 'rect',
  },

  // --- Environment -------------------------------------------------------
  {
    id: 'urban',
    name: 'Urban growth',
    blurb: 'How much built surface has been recorded here over time.',
    sector: 'Environment & climate',
    factors: ['lc_built_pct', 'built_volume', 'population_density', 'nightlight_radiance'],
    tool: 'rect',
  },
  {
    id: 'heat',
    name: 'Urban heat',
    blurb: 'How much hotter is this area than its surroundings?',
    sector: 'Environment & climate',
    factors: ['lst_day', 'heat_anomaly', 'lc_tree_pct', 'impervious_pct'],
    tool: 'rect',
  },
  {
    id: 'carbon',
    name: 'Carbon and canopy',
    blurb: 'What is standing here, and what is it holding?',
    sector: 'Environment & climate',
    factors: ['canopy_height_mean', 'canopy_cover_pct', 'carbon_stock',
              'above_ground_biomass', 'sequestration_rate', 'lc_tree_pct'],
    tool: 'freehand',
  },
  {
    id: 'air-quality',
    name: 'Air quality',
    blurb: 'What is in the air here, and where does it come from?',
    sector: 'Environment & climate',
    factors: ['no2', 'pm25', 'pm10', 'road_density', 'population_density', 'lc_tree_pct'],
    tool: 'rect',
  },
]

/** Templates in the order the sidebar shows them, grouped by sector. */
export function templatesBySector(): [string, Template[]][] {
  const out = new Map<string, Template[]>()
  for (const t of TEMPLATES) {
    if (!out.has(t.sector)) out.set(t.sector, [])
    out.get(t.sector)!.push(t)
  }
  return [...out.entries()]
}
