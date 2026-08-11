# Imagery

**You supply the pictures. Nothing here is generated, and nothing is a
stand-in.** Every slot on the public site either shows a file you dropped in
here, or shows a labelled frame naming the file it is waiting for. There is no
state where the site displays invented imagery.

## How to add or replace a picture

1. Drop the file into the right folder, under **exactly** the filename below.
2. Run `npm run assets` — or just `npm run dev` / `npm run build`, which do it
   for you.
3. Open `src/site/assets.ts` and rewrite that slot's `alt` to describe what your
   photograph actually shows, and add a `credit` if the image needs one.

Replacing a picture later is dropping a new file over the old one. Same name,
no code change.

The terminal prints a checklist on every build — what is supplied, what is
still missing, and any file in these folders that no slot points at (usually a
typo, or an `IMG_4821.JPG` dropped in hopefully).

## The files

Sizes are the largest we will ever display; export at least that wide. Ratios
are what the frame reserves, so a file at the wrong ratio will be cropped to
fill, from the centre.

### `hero/` — the landing frame

| File | Ratio | Min width | What it is |
| --- | --- | --- | --- |
| `hero-loop.mp4` | 16:9 | 2400 | Short seamless loop, 8–15s, **no audio**, no camera shake. Aerial or drone over landscape. |
| `hero-loop-poster.jpg` | 16:9 | 2400 | First frame of the loop. Shown while it loads, and instead of it for anyone who has asked for reduced motion. |
| `hero-aerial.jpg` | 16:9 | 2400 | Used if there is no loop. One strong aerial or satellite frame. |

Until one of these exists the hero renders the generated field sheet — the
topographic map of England and Wales. That is a finished design, not a
placeholder, so there is no rush; supply a loop when you have one worth using.

### `product/` — the instrument

| File | Ratio | Min width | What it is |
| --- | --- | --- | --- |
| `interface-site-report.png` | 16:10 | 1600 | Screenshot of the real report panel. Take it at 1440×900 from `/app` with a site drawn. |
| `interface-map-canvas.png` | 16:10 | 1600 | Screenshot of the map with a drawn area and cells shaded. |
| `satellite-imagery.jpg` | 1:1 | 1200 | True-colour satellite over farmland or mixed land use. |
| `terrain-contour-map.jpg` | 1:1 | 1200 | Topographic sheet — contour lines, ideally a real or archival survey. |
| `land-analysis-overlay.jpg` | 1:1 | 1200 | Analysis over a real place: habitat polygons, parcels, a classification raster. |

### `field/` — the fieldwork

| File | Ratio | Min width | What it is |
| --- | --- | --- | --- |
| `fieldwork-survey.jpg` | 4:5 | 1400 | Real fieldwork. Someone working, not posing. Weather and mud are the point. |
| `field-notebook.jpg` | 4:5 | 1400 | Handwriting, sketches, coffee rings. Shot flat, top down. |
| `gps-equipment.jpg` | 1:1 | 1200 | GPS, total station, quadrat, soil auger. Close, plain ground if possible. |
| `landscape-wide.jpg` | 21:9 | 2400 | Wide, horizontal, room for type across it. A place someone has to assess, not a beauty shot. |

This section renders on deep forest, so images with dark or moody tone sit
better here than bright ones.

### `marketing/` — the argument

| File | Ratio | Min width | What it is |
| --- | --- | --- | --- |
| `site-before-analysis.jpg` | 4:3 | 1400 | Plain aerial of a site, nothing drawn on it. |
| `site-after-analysis.jpg` | 4:3 | 1400 | **The same frame, same angle**, with the analysis on it. The pair only works if they match. |
| `archival-map.jpg` | 3:2 | 1600 | Old paper map, plan or estate drawing. Texture matters more than legibility. |
| `property-landscape.jpg` | 3:2 | 1600 | The commercial subject: a farm, an estate, a development site. |

## Composition is yours

Each plate takes props in `Pages.tsx` controlling how it sits on the page:

- `tilt={-2}` — degrees of rotation. Small numbers; past about 4 it reads as a
  mistake rather than as a pinned print.
- `tape="tl" | "tr" | "both"` — a strip of masking tape across a corner.
- `torn` — torn paper edge along the bottom.
- `halftone` — print dot screen, for the archival plates.
- `overlap` — pull the plate up into the one above it.
- `caption="..."` — printed across the bottom.

Change those freely. They are the collage vocabulary, and none of them applies
unless asked for, so the mess stays composed rather than automatic.

## Rules worth keeping

**No external URLs.** Everything is served from this site's own origin. An
image on someone else's CDN is an outage you do not control and a record of
your visitors on a server you do not own — and the content policy in
`vercel.json` blocks it anyway.

**Alt text describes the real photograph.** The text currently in
`src/site/assets.ts` describes what each slot is *for*. Once a real image lands,
rewrite it to describe that image. Someone using a screen reader gets that
sentence instead of the picture.

**Credit what needs crediting.** If an image is licensed, or someone took it,
put them in the slot's `credit` field. It prints in a credits line under the
marketing section. A product this careful about where its data comes from
should be equally careful about where its pictures come from.

**These files are not in git.** Photographs and video are large binaries and
`.gitignore` excludes them, so a clone will show the awaiting frames until the
assets are put in place. If you want them versioned, set up `git-lfs` and do it
deliberately — rather than by committing a 40 MB mp4 once and discovering it in
every clone forever.
