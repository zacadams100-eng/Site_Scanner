/**
 * Every image and video on the public site, in one table.
 *
 * ## The rule
 *
 * **Nothing here is generated, and nothing here is a stand-in for a photograph
 * that does not exist.** A slot either points at a real file you supplied, or
 * it renders as a labelled empty frame telling you which file to drop in.
 * There is no third state where the site shows something invented and hopes
 * nobody asks where it came from.
 *
 * ## How to fill a slot
 *
 * 1. Put the file in `public/assets/<section>/` under exactly the `file` name
 *    below. Descriptive names, no hashes, no `image-1.jpg`.
 * 2. Run `npm run assets` (or just `npm run dev` / `npm run build` — both do
 *    it) to pick it up.
 * 3. Edit the `alt` and `credit` here. That is the only step a build cannot do
 *    for you: alt text describes what *your* photograph shows, and a credit is
 *    a fact about where it came from.
 *
 * Replacing a picture is dropping a file with the same name. No code changes,
 * no imports, no rebuild of anything but the manifest.
 *
 * ## Why alt and credit live in code rather than beside the file
 *
 * They are content, they need review, and they belong in version control where
 * a change to them shows up in a diff. A caption sitting in a sidecar file
 * next to a JPEG is a caption nobody ever reads again.
 */

export type AssetKind = 'image' | 'video'

export interface AssetSlot {
  /** Stable id used in markup. Never changes, even if the file does. */
  id: string
  kind: AssetKind
  /** Folder under `public/assets/`. */
  section: 'hero' | 'product' | 'evidence' | 'field' | 'marketing' | 'brand'
  /** Exact filename to drop in. Extension included — swap it here if you
   *  supply a different format. */
  file: string
  /** A still frame for a video, shown while it loads and wherever motion is
   *  refused. A video slot without one is a black rectangle on first paint. */
  poster?: string
  /** What the picture shows, for a reader who cannot see it. Written for the
   *  real photograph once it exists — the text below describes the intent and
   *  should be rewritten to describe the actual image. */
  alt: string
  /** Photographer, licence, or source. Shown in the page's credits block.
   *  Empty means unattributed, which is a choice rather than an oversight. */
  credit?: string
  /** What this slot is for, shown on the empty frame so the placeholder tells
   *  you what to shoot rather than just that something is missing. */
  brief: string
  /** Rendered aspect ratio. The frame reserves this space whether or not the
   *  file exists, so dropping one in never reflows the page. */
  ratio: string
  /** Longest edge we will ever display it at, so you know what to export. */
  maxWidth: number
}

export const ASSETS = {
  /* ------------------------------------------------------------------ hero */

  heroVideo: {
    id: 'heroVideo', kind: 'video', section: 'hero',
    file: 'hero-loop.mp4', poster: 'hero-loop-poster.jpg',
    alt: 'Aerial footage of open country, drifting slowly.',
    brief: 'Short seamless loop, 8–15s, no audio, no camera shake. Aerial or '
      + 'drone over landscape. Muted and analogue rather than glossy stock.',
    ratio: '16 / 9', maxWidth: 2400,
  },
  heroStill: {
    id: 'heroStill', kind: 'image', section: 'hero',
    file: 'hero-aerial.jpg',
    alt: 'Aerial photograph of the landscape Site Scanner reads.',
    brief: 'The fallback when there is no loop, and the poster behind it. One '
      + 'strong aerial or satellite frame.',
    ratio: '16 / 9', maxWidth: 2400,
  },

  /* --------------------------------------------------------------- product */

  /*
   * Six screenshots of the running application.
   *
   * **These must come from a deployment with real data.** The demo backend
   * stamps every response `X-Contour-Mock: true` and the interface labels it
   * "Demo data — generated on the server", so a screenshot taken against it
   * shows invented findings with a badge saying so. Putting that on a
   * marketing page is either a lie or an advert for the disclaimer. See the
   * capture instructions in public/assets/README.md.
   */
  productLand: {
    id: 'productLand', kind: 'image', section: 'product',
    file: 'workspace-land.png',
    alt: 'The Land scanner workspace: a drawn site on the map beside its report.',
    brief: 'Land workspace at 1440x900. Real site drawn, map and report both '
      + 'visible, findings present, evidence coverage above zero.',
    ratio: '16 / 10', maxWidth: 2880,
  },
  productHabitat: {
    id: 'productHabitat', kind: 'image', section: 'product',
    file: 'workspace-habitat.png',
    alt: 'The Habitat scanner workspace assessing ecological condition.',
    brief: 'Habitat workspace at 1440x900, same requirements as Land. The '
      + 'HABITAT badge must be legible — it is what shows this is a platform.',
    ratio: '16 / 10', maxWidth: 2880,
  },
  productOverview: {
    id: 'productOverview', kind: 'image', section: 'product',
    file: 'report-site-overview.png',
    alt: 'The site overview: area, coordinates, evidence coverage and finding states.',
    brief: 'The Overview tab, panel only. Must show real coverage and the four '
      + 'finding states with non-zero counts.',
    ratio: '4 / 5', maxWidth: 1400,
  },
  productRadar: {
    id: 'productRadar', kind: 'image', section: 'product',
    file: 'report-radar.png',
    alt: 'The investigation radar, showing which topics were assessed and which were not.',
    brief: 'The Radar tab. Needs a mix of states — flagged, checked and clear, '
      + 'and not assessed — or it does not make the point.',
    ratio: '4 / 5', maxWidth: 1400,
  },
  productEvidence: {
    id: 'productEvidence', kind: 'image', section: 'product',
    file: 'report-evidence.png',
    alt: 'The evidence drawer: a finding traced to its source and its limits.',
    brief: 'Evidence drawer open on a real finding, showing the source, the '
      + 'measurement and the "does not establish" statement.',
    ratio: '4 / 5', maxWidth: 1400,
  },
  productInvestigation: {
    id: 'productInvestigation', kind: 'image', section: 'product',
    file: 'workspace-investigation.png',
    alt: 'The investigation workspace, listing what a professional should check next.',
    brief: 'Investigation workspace with real investigations open, each traced '
      + 'back to the findings that raised it.',
    ratio: '16 / 10', maxWidth: 2880,
  },

  /* -------------------------------------------------------------- evidence */

  /* The raw material a scan reads. These are not product screenshots and can
     be sourced independently — open imagery, archival sheets, your own
     photography. */
  evidenceSatellite: {
    id: 'evidenceSatellite', kind: 'image', section: 'evidence',
    file: 'satellite-imagery.jpg',
    alt: 'True-colour satellite imagery of farmland.',
    brief: 'Sentinel-2 or equivalent over mixed land use. Square crop.',
    ratio: '1 / 1', maxWidth: 1200,
  },
  evidenceTerrain: {
    id: 'evidenceTerrain', kind: 'image', section: 'evidence',
    file: 'terrain-elevation.jpg',
    alt: 'Elevation and terrain across a river valley.',
    brief: 'Hillshade, DEM or a contour sheet. Square crop.',
    ratio: '1 / 1', maxWidth: 1200,
  },
  evidenceVegetation: {
    id: 'evidenceVegetation', kind: 'image', section: 'evidence',
    file: 'vegetation-index.jpg',
    alt: 'A vegetation index raster showing growth across a season.',
    brief: 'NDVI/EVI raster, or a false-colour composite. Square crop.',
    ratio: '1 / 1', maxWidth: 1200,
  },
  evidenceHydrology: {
    id: 'evidenceHydrology', kind: 'image', section: 'evidence',
    file: 'hydrology-water.jpg',
    alt: 'Watercourses and flood extent across low ground.',
    brief: 'Rivers, flood zones or surface water. Square crop.',
    ratio: '1 / 1', maxWidth: 1200,
  },
  evidenceHistorical: {
    id: 'evidenceHistorical', kind: 'image', section: 'evidence',
    file: 'historical-imagery.jpg',
    alt: 'A historical aerial photograph of the same ground.',
    brief: 'Archival aerial or an old OS sheet of somewhere you also have '
      + 'current imagery for. Square crop.',
    ratio: '1 / 1', maxWidth: 1200,
  },

  /* ----------------------------------------------------------------- field */

  fieldSurvey: {
    id: 'fieldSurvey', kind: 'image', section: 'field',
    file: 'fieldwork-survey.jpg',
    alt: 'An ecologist recording observations in the field.',
    brief: 'Real fieldwork. Someone working, not posing. Weather and mud are '
      + 'the point.',
    ratio: '4 / 5', maxWidth: 1400,
  },
  fieldEquipment: {
    id: 'fieldEquipment', kind: 'image', section: 'field',
    file: 'gps-equipment.jpg',
    alt: 'Survey GPS equipment set up on a tripod.',
    brief: 'GPS, total station, quadrat, soil auger — instruments, close, on a '
      + 'plain ground if possible.',
    ratio: '1 / 1', maxWidth: 1200,
  },
  fieldLandscape: {
    id: 'fieldLandscape', kind: 'image', section: 'field',
    file: 'landscape-wide.jpg',
    alt: 'A wide landscape under changing weather.',
    brief: 'Wide, horizontal, room for type across it. Not a beauty shot — a '
      + 'place someone has to assess.',
    ratio: '21 / 9', maxWidth: 2400,
  },
  fieldNotebook: {
    id: 'fieldNotebook', kind: 'image', section: 'field',
    file: 'field-notebook.jpg',
    alt: 'A field notebook with handwritten survey records.',
    brief: 'Handwriting, sketches, coffee rings. Shot flat, top down.',
    ratio: '4 / 5', maxWidth: 1400,
  },

  /* ------------------------------------------------------------- marketing */

  /*
   * Then and now.
   *
   * **Only a comparison the product can substantiate.** The pair has to be the
   * same ground, the same footprint, and a change Site Scanner would actually
   * report — not two dramatic photographs of different places. If the honest
   * answer is that nothing much changed, that is the pair to use: a site where
   * the evidence says "no material change" is a result, and faking a collapse
   * because it looks better on a homepage is the exact failure this product
   * exists to avoid.
   *
   * Set `changeCaption` on each to the real dates. They print on the plates.
   */
  changeThen: {
    id: 'changeThen', kind: 'image', section: 'marketing',
    file: 'change-then.jpg',
    alt: 'The site as recorded in the earlier of the two observations.',
    brief: 'Earlier observation. Note the real date — it prints on the plate. '
      + 'Sentinel-2 starts 2017; older needs aerial or archival.',
    ratio: '4 / 3', maxWidth: 1400,
  },
  changeNow: {
    id: 'changeNow', kind: 'image', section: 'marketing',
    file: 'change-now.jpg',
    alt: 'The same site in the most recent observation, at the same extent.',
    brief: 'Same ground, same footprint, same angle. If the two do not line up '
      + 'the comparison is worthless.',
    ratio: '4 / 3', maxWidth: 1400,
  },
  marketingMap: {
    id: 'marketingMap', kind: 'image', section: 'marketing',
    file: 'archival-map.jpg',
    alt: 'An archival map of the surveyed region.',
    brief: 'Old paper map, plan or estate drawing. Texture matters more than '
      + 'legibility.',
    ratio: '3 / 2', maxWidth: 1600,
  },
  marketingProperty: {
    id: 'marketingProperty', kind: 'image', section: 'marketing',
    file: 'property-landscape.jpg',
    alt: 'Land and buildings of the kind clients commission surveys on.',
    brief: 'The commercial subject: a farm, an estate, a development site.',
    ratio: '3 / 2', maxWidth: 1600,
  },
} as const satisfies Record<string, AssetSlot>

export type AssetId = keyof typeof ASSETS

/** Public URL for a slot's file. Always site-relative — **never** an external
 *  host. An image on someone else's CDN is an outage and a privacy leak we do
 *  not control, and the content policy in vercel.json blocks it anyway. */
export function assetUrl(slot: AssetSlot, which: 'file' | 'poster' = 'file'): string {
  const name = which === 'poster' ? slot.poster : slot.file
  return name ? `/assets/${slot.section}/${name}` : ''
}

/** Slots grouped by section, for the credits block and the asset checklist. */
export function slotsBySection(section: AssetSlot['section']): AssetSlot[] {
  return Object.values(ASSETS).filter((a) => a.section === section)
}
