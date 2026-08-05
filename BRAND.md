# Site Scanner — brand and interface

The specification this implements, and where each rule actually lives in the
code. `web/src/index.css` is the source of truth; this file explains it.

The test for every decision below: **does it help someone understand spatial
data?** If not, it was simplified or removed.

---

## What it should feel like

Software for environmental consultants, ecologists, planners and GIS
professionals. Scientific, professional, calm, precise. Users sit in front of
it for hours, so the interface has to be quiet enough to disappear.

Reference points: field notebooks, survey instruments, natural history
publications, modern scientific software.

Explicitly not: AI gradients, neon, glassmorphism, heavy animation, big
shadows, bright dashboards, anything "cyber". The previous interface was a
dark canvas with copper accents and backdrop blur on every floating surface —
handsome, and the opposite of this.

---

## Colour

| Token | Value | Where |
| --- | --- | --- |
| Paper | `#F8F6F2` | The ground everything sits on |
| Sidebar | `#4D6048` | Structure: rail, primary buttons, drawn area |
| Ink | `#232323` | Primary text |
| Slate | `#69706A` | Secondary text |
| Rule | `#DDD8CF` | Every border and divider |
| Accent | `#2FA8D8` | "Here, now" only — selection, focus, the time head |
| Success | `#72965E` | A factor backed by real observations |
| Warning | `#C89C42` | Caveats: partial years, demo data |
| Error | `#C45A5A` | Failures |

Roughly 95% neutral, 5% colour. Two rules keep it that way:

**Structure is moss; the accent is blue.** The sidebar, primary buttons and the
drawn shape are green because they are furniture. Blue means the thing you are
pointing at right now. They never compete because they never mean the same
thing.

**Colour is reserved for data.** The value ramp (`web/src/lib/format.ts`) runs
pale-paper → moss → deep instrument blue, with lightness falling monotonically
so the ordering survives greyscale printing and colour-blind reading.

Both the accent and the warning colours are darkened from the brand swatch for
small text (`--blue-700`, `--amber-600`), because 11px type at the display
value does not clear WCAG AA on paper. The swatch values remain in the palette
for fills and borders, where contrast is not a legibility question.

---

## Type

| Face | Job |
| --- | --- |
| IBM Plex Sans | Interface: headings, navigation, buttons, labels |
| Inter | Prose: descriptions, notes, help text |
| IBM Plex Mono | Measurement, and only measurement |

Mono is the rule that does the most work. Coordinates, scale, CRS, zoom, cell
counts, areas, factor values, ids, file names and licence notices are set in
mono; a number inside a sentence is not. It is how the interface distinguishes
a figure you could act on from a figure you are reading about.

All three are self-hosted (`@fontsource`, imported in `web/src/main.tsx`) — a
font CDN would be a third-party request the published build's content policy
blocks, and a webfont that silently fails takes the brand with it.

---

## Layout

```
┌───────────────────── top bar 64 ──────────────────────┐
│ rail 280 │      stage (map + timeline)      │  panel  │
└───────────────────── status 28 ───────────────────────┘
```

- **Top bar (64px)** — mark, wordmark, the open site's name, place search, and
  the badges that say what the data is.
- **Left sidebar (280px, collapsible to 56px)** — Layers, Sites, Data,
  Analysis. Moss, because it is the one piece of furniture that should read as
  the product.
- **Stage** — the map, a floating tool rail, and the timeline.
- **Report panel (440px, closable)** — the table, charts and sources.
- **Status bar (28px)** — latitude, longitude, scale, zoom, CRS, cell count and
  connection state. All measurement, so all mono.

The brief asks for the map to hold 80–90% of the screen. Rather than fix a
ratio, both columns collapse: with the rail folded and the report closed the
map takes ~96% of a desktop window, and the layout never squeezes the map to
make room for chrome.

Below 900px the rail becomes icons with an overlay panel and the report becomes
a sheet — both stopping above the timeline, because a temporal tool whose time
control is behind a panel is not a temporal tool.

---

## Components

- **Cards**: white, 1px `#DDD8CF`, 10px radius, shadow so faint it only
  disambiguates overlap.
- **Buttons**: primary is moss with white text; secondary is transparent with a
  rule border and a paper hover.
- **Icons**: outline, 2px, rounded joins, drawn on a 24 grid. No filled icons,
  no 3D, no cartoons.
- **Tables**: alternating row shading, sticky headers, sortable columns,
  tabular numerals, minimal borders.
- **Layers**: visibility, symbology preview, name, source, and an opacity
  slider for the overlay. The first layer is the one painted on the map.
- **Motion**: 150–240ms, opening panels and hover states only. Anyone who has
  asked their system for reduced motion gets none of it.

---

## The mark

A dart frog drawn as a specimen plate: flat silhouette, eyes above the head
line, contour rings across the back — the one place the map appears in the
mark. Geometric and minimal; not cute, not aggressive.

It exists twice on purpose: `web/src/components/BrandMark.tsx` for the
interface and `web/public/favicon.svg` for the browser, which needs a static
file before any JavaScript runs. **If one changes, change both.**

It was checked at 16, 32, 64 and 160px. An earlier version used two arcs across
the back, which at large sizes read as a mouth and turned the mark into a
cartoon; concentric contour rings say "topography" instead.

---

## Accessibility

- Every text/background pair in the interface meets WCAG AA at its own size,
  checked numerically rather than by eye.
- Visible focus rings on everything focusable, `:focus-visible` so a mouse user
  is not followed around by them.
- The timeline is a real `<input type="range">` under its custom rendering, so
  keyboard and screen readers work without reimplementation.
- Full keyboard control of time: arrows step a month, PgUp/PgDn a year,
  Home/End jump, space plays.

---

## Responsive

Desktop first. Tablet fully supported. Phone works — drawing, reading,
comparing and saving all verified at 390px — but it is not what the product is
designed around.
