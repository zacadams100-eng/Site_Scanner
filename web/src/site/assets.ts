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
  section: 'hero' | 'product' | 'field' | 'marketing' | 'brand'
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

  productReport: {
    id: 'productReport', kind: 'image', section: 'product',
    file: 'interface-site-report.png',
    alt: 'The Site Scanner report panel, showing evidence coverage and findings.',
    brief: 'Screenshot of the real report panel. Take it at 1440x900 from '
      + '/app with a site drawn.',
    ratio: '16 / 10', maxWidth: 1600,
  },
  productMap: {
    id: 'productMap', kind: 'image', section: 'product',
    file: 'interface-map-canvas.png',
    alt: 'The Site Scanner map with a drawn site and its value overlay.',
    brief: 'Screenshot of the map half with a drawn area and cells shaded.',
    ratio: '16 / 10', maxWidth: 1600,
  },
  productSatellite: {
    id: 'productSatellite', kind: 'image', section: 'product',
    file: 'satellite-imagery.jpg',
    alt: 'Satellite imagery of a parcel of land.',
    brief: 'True-colour satellite over farmland or mixed land use. This is the '
      + 'raw material a scan reads.',
    ratio: '1 / 1', maxWidth: 1200,
  },
  productTerrain: {
    id: 'productTerrain', kind: 'image', section: 'product',
    file: 'terrain-contour-map.jpg',
    alt: 'A contour map of hill terrain.',
    brief: 'Topographic sheet, contour lines, ideally a real OS-style or '
      + 'archival survey sheet.',
    ratio: '1 / 1', maxWidth: 1200,
  },
  productAnalysis: {
    id: 'productAnalysis', kind: 'image', section: 'product',
    file: 'land-analysis-overlay.jpg',
    alt: 'Land classification overlaid on aerial imagery.',
    brief: 'Analysis output over a real place — habitat polygons, parcels or a '
      + 'classification raster.',
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

  beforeAnalysis: {
    id: 'beforeAnalysis', kind: 'image', section: 'marketing',
    file: 'site-before-analysis.jpg',
    alt: 'A site as it appears before any analysis has been applied.',
    brief: 'Left half of the before/after. Plain aerial of a site, nothing '
      + 'drawn on it.',
    ratio: '4 / 3', maxWidth: 1400,
  },
  afterAnalysis: {
    id: 'afterAnalysis', kind: 'image', section: 'marketing',
    file: 'site-after-analysis.jpg',
    alt: 'The same site with constraints, boundaries and findings drawn over it.',
    brief: 'Right half of the before/after. The same frame with the analysis '
      + 'on it — must be the same place at the same angle.',
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
