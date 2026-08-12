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

### `product/` — the application itself

**These are the most important assets on the site, and they cannot be faked.**

| File | Ratio | Min width | What it is |
| --- | --- | --- | --- |
| `workspace-land.png` | 16:10 | 2880 | Land workspace at 1440×900. Real site drawn, map and report both visible, findings present, coverage above zero. |
| `workspace-habitat.png` | 16:10 | 2880 | Habitat workspace, same requirements. The HABITAT badge must be legible — it is what shows this is a platform rather than one tool. |
| `report-site-overview.png` | 4:5 | 1400 | The Overview tab, panel only. Real coverage, four finding states with non-zero counts. |
| `report-radar.png` | 4:5 | 1400 | The Radar tab. Needs a mix of flagged, checked-and-clear and not-assessed, or it makes no point. |
| `report-evidence.png` | 4:5 | 1400 | Evidence drawer open on a real finding: source, measurement, and the "does not establish" statement. |
| `workspace-investigation.png` | 16:10 | 2880 | Investigation workspace, investigations traced back to the findings that raised them. |

#### What is required to capture these

The demo backend cannot produce them. It stamps every response
`X-Contour-Mock: true`, the interface labels the result *"Demo data — generated
on the server"*, and the findings are invented. A screenshot of that on a
marketing page is either dishonest or an advertisement for the disclaimer.

To take these screenshots you need, in order:

1. **A Google Cloud project with Earth Engine enabled**, and a service-account
   key. `app.py` reads `GOOGLE_APPLICATION_CREDENTIALS_JSON` and `EE_PROJECT`;
   `DEPLOY.md` has the setup.
2. **The real backend running** — `uvicorn app:app`, not `mock_ee_backend`.
   Confirm with `curl -sD- localhost:8000/api/catalog -o /dev/null | grep -i
   contour-mock`: it must be **absent or false**. If it says `true` you are
   still on the mock.
3. **A real site in England** drawn in the workspace, on ground where the
   evidence is interesting enough to produce findings. A field with nothing on
   it produces an honest and completely unpersuasive report.
4. **Retina capture at 2×** — 2880×1800 for a 1440×900 window, so the interface
   text stays sharp.

Note that only 28 of Land's 271 factors are real today, and 11 of those are
`verified` (actually run against the live service) rather than `written`. The
report will be mostly "not assessed", and **that is the honest picture** — the
radar exists to show exactly that. Do not select a factor set to hide it.

### `evidence/` — what a scan reads

Not product screenshots. These can be sourced independently — open imagery,
archival sheets, your own captures. Square crops, shown as a contact sheet.

| File | Ratio | Min width | What it is |
| --- | --- | --- | --- |
| `satellite-imagery.jpg` | 1:1 | 1200 | Sentinel-2 or equivalent over mixed land use. |
| `terrain-elevation.jpg` | 1:1 | 1200 | Hillshade, DEM or a contour sheet. |
| `vegetation-index.jpg` | 1:1 | 1200 | NDVI/EVI raster or a false-colour composite. |
| `hydrology-water.jpg` | 1:1 | 1200 | Rivers, flood zones or surface water. |
| `historical-imagery.jpg` | 1:1 | 1200 | Archival aerial or an old OS sheet — ideally somewhere you also have current imagery for. |

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
| `change-then.jpg` | 4:3 | 1400 | The earlier observation. Note the real date. Sentinel-2 starts 2017; older than that needs aerial or archival. |
| `change-now.jpg` | 4:3 | 1400 | **The same ground, same footprint, same angle**, most recent observation. If the two do not line up the comparison is worthless. |
| `archival-map.jpg` | 3:2 | 1600 | Old paper map, plan or estate drawing. Texture matters more than legibility. |
| `property-landscape.jpg` | 3:2 | 1600 | The commercial subject: a farm, an estate, a development site. |

**Only a comparison the product could substantiate.** If the honest answer is
that nothing much changed, that is the pair to use — a site where the evidence
says "no material change" is a result. Manufacturing a dramatic collapse
because it looks better on a homepage is the exact failure this product exists
to prevent.

## Supply order

All 21 slots are unsupplied. Ranked by what a visitor sees first and what the
site cannot argue without — supply top to bottom and each one earns its place
before the next.

| # | Slot | Where | Why here |
| --- | --- | --- | --- |
| 1 | `product/workspace-land.png` | The instrument | The site claims a working instrument and currently shows a frame describing one. This is the single most valuable file on the list. **Blocked on Earth Engine — see below.** |
| 2 | `product/workspace-habitat.png` | The instrument | Proves it is a platform rather than one tool. **Blocked.** |
| 3 | `hero/hero-loop.mp4` + `hero-loop-poster.jpg` | Hero | First thing anyone sees. Until it exists the generated field sheet holds the space, and that is a finished design — so this is high value, not urgent. |
| 4 | `evidence/satellite-imagery.jpg` | The instrument | First of the contact sheet beside the interface. Sourceable today. |
| 5 | `evidence/terrain-elevation.jpg` | The instrument | Sourceable today. |
| 6 | `evidence/vegetation-index.jpg` | The instrument | Sourceable today. |
| 7 | `product/report-radar.png` | The assessment | Carries the coverage-before-findings argument. **Blocked.** |
| 8 | `product/report-evidence.png` | The assessment | Shows a finding traced to its source. **Blocked.** |
| 9 | `marketing/change-then.jpg` | The change | Half of the before/after. Useless without its pair. |
| 10 | `marketing/change-now.jpg` | The change | The other half. Same ground, same footprint. |
| 11 | `field/fieldwork-survey.jpg` | Field record | Anchors the inverted spread. Sourceable today. |
| 12 | `field/landscape-wide.jpg` | Field record | Wide plate, sets the section's tone. |
| 13 | `product/report-site-overview.png` | The assessment | **Blocked.** |
| 14 | `product/workspace-investigation.png` | The assessment | **Blocked.** |
| 15 | `evidence/hydrology-water.jpg` | The instrument | Completes the contact sheet. |
| 16 | `evidence/historical-imagery.jpg` | The instrument | Completes the contact sheet. |
| 17 | `field/field-notebook.jpg` | Field record | Character rather than argument. |
| 18 | `field/gps-equipment.jpg` | Field record | Character rather than argument. |
| 19 | `marketing/archival-map.jpg` | The change | Texture. |
| 20 | `marketing/property-landscape.jpg` | The change | Texture. |
| 21 | `hero/hero-aerial.jpg` | Hero | Only needed if there is no loop. |

**Six of the top fourteen are blocked on Earth Engine credentials** (see
`docs/EE_SETUP.md`). A screenshot taken against the demo backend shows invented
findings with a badge admitting it, so those slots stay empty until real data
exists.

**Nine can be supplied today** without any dependency: the five evidence
squares, the four field photographs. Those are the fastest way to make the site
stop reading as a shot list.

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
