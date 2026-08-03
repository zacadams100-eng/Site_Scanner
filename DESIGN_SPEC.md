# Feature specification & UI/UX plan

A map-based project and data tool for people who are not GIS professionals.

Written against the code that exists (`web/src/`), not from a blank page —
roughly half of what follows is already built and needs extending rather than
inventing. Each section says which.

---

## 0. Two things to settle before building anything

### "Project management" is doing a lot of work in that sentence

It has two readings, and they are weeks apart:

| Reading | What it means | Effort |
| --- | --- | --- |
| **Saved workspaces** | A project is a named map view + chosen layers + charts, that you reopen later | ~1 week; `Toolbar.tsx` already saves AOIs to `localStorage`, which is the seed |
| **Actual project management** | Tasks, assignees, due dates, comments, notifications, permissions | Months, and a different product |

Everything below assumes **saved workspaces**, because that is what the rest of
the brief describes. If you meant tasks and collaboration, say so — it changes
the data model, adds accounts and permissions as hard requirements, and makes
the home page a very different screen.

### The three data domains do not belong to the same product yet

Property, construction/industry and commodity trading are three different
businesses with three different buyers:

- **Property** — parcels and prices. Polygons, joined to sales data.
- **Construction & industry** — sites and planning applications. Points with a
  status and a date.
- **Commodity trading** — flows between places. Origin→destination arcs with a
  volume and a price, which is a *fundamentally different map* from the other
  two. It is not really about where you drew a shape.

Commodity trading is the odd one out. It answers "what moved from here to
there" rather than "what is here". Forcing it into a draw-an-area interface is
where this design will fight itself hardest.

**Recommendation:** build the layer *system* so all three fit, but ship one
domain properly first. Property is the natural choice — it shares a data shape
with what already works, and HM Land Registry Price Paid Data is already wired
up in `app.py`.

---

## 1. Onboarding tutorial

### How it should look

Not a carousel of screenshots, and not a video. **Coach marks over the real
interface**, with a real project already loaded.

A small card (roughly 300 px wide) anchored next to the thing it is describing,
with everything else dimmed but still visible. Inside the card: one short
sentence, a step counter (`2 of 5`), a primary **Next**, and a quiet **Skip
tour** that is present on every single step.

### How it should behave

The single most important decision: **step 1 creates a sample project.** Never
onboard someone onto an empty screen — there is nothing to point at, and the
first thing they do after the tour ends is face a blank page anyway.

Five steps, maximum:

1. "This is your map. Drag to move, scroll or use +/− to zoom in." *(anchors the map)*
2. "Turn data on and off here." *(anchors the layer switch, toggles one on so they see it happen)*
3. "Draw a shape to study an area." *(anchors the draw tools — and **waits for them to actually draw one**)*
4. "Your results appear here, and update as you change things." *(anchors the data panel)*
5. "Everything saves automatically. Find your projects here." *(anchors Home)*

Step 3 is a **do-it-with-me** step: the tour pauses until the user completes
the action. People remember what their hands did, not what they read. The other
four are read-and-continue.

Revisiting: a permanent **Help → Show me around** in the header. Not buried in
settings, not a floating chat bubble.

Abandonment: if someone skips or drops out at step 3, store that. Next visit,
offer once — *"Pick up where you left off?"* — and never ask again if declined.

### Technical & design considerations

- **Anchoring is the hard part.** Coach marks need `getBoundingClientRect` plus
  a `ResizeObserver` and a scroll listener, or the card drifts off its target on
  window resize. Render into a portal at the document root so it escapes any
  `overflow: hidden` ancestor.
- **Accessibility:** trap focus inside the card, announce each step through an
  `aria-live="polite"` region, bind `Esc` to skip. A tour that traps keyboard
  users is worse than no tour.
- `prefers-reduced-motion` must disable the dim/spotlight transition.
- **Do not gate the app behind it.** Every step is dismissible; the underlying
  UI stays interactive.
- Store completion server-side once accounts exist, not just `localStorage` —
  otherwise it reappears on every new device and reads as a bug.

---

## 2. Home page — project hub

### How it should look

A dashboard of project cards on a calm, wide-margin page. Each card:

- **Map thumbnail** — a snapshot of that project's view, captured on save
- **Project name**, large and editable in place
- **Last opened** in plain words: "Yesterday", "3 days ago" — not a timestamp
- A quiet metadata line: "4 layers · 2 charts"
- A `⋯` menu, always visible (hover-only actions fail on touch entirely)

The **New project** button is a large primary card in the first grid position,
not a button in a toolbar. It should be the most obvious thing on the screen.

### How it should behave

**The empty state is the most important screen in the product.** A first-time
user sees it immediately after the tour. It should not say "No projects". It
should be a headline — *"Start your first project"* — with three starter cards:

> **Look at a property area** · **Track construction nearby** · **Start from a blank map**

Picking one creates the project *and* preloads the right layers, which is
exactly the pattern `Templates.tsx` already implements for factor selection.

Other behaviour:

- **Autosave.** No save button. The word "saved" appears briefly after changes.
- **Delete offers undo, not confirmation.** A toast — *"Project deleted. Undo"* —
  for 10 seconds. Confirmation dialogs train people to click through without
  reading; undo actually protects them.
- **Duplicate** matters more than people expect. Users experiment by copying a
  project they do not want to break.
- **Search appears only above ~8 projects.** Progressive disclosure: an empty
  search box next to two projects is visual noise.
- Sort by recent, always, with name as the only alternative.

### Technical & design considerations

- Data model: `{ id, name, view: {center, zoom}, aoi, layers[], charts[], thumbnail, createdAt, updatedAt }`.
- **Thumbnails** are a disproportionate quality win. Capture the map canvas on
  save, downscale to ~400 px, store as a data URL (or blob in object storage
  once there are accounts). A wall of identical grey cards feels unfinished; a
  wall of little maps feels like a real tool.
- Optimistic UI on rename and delete — never make someone wait on the network
  for something that cannot really fail.
- Route as `/projects` and `/projects/:id`, so the browser back button behaves
  and links are shareable. `lib/permalink.ts` already encodes view state and
  extends naturally.

---

## 3. Chart creation

### The conflict, stated plainly

The brief asks for two things in tension: *"similar in function to Excel
charts"* and *"minimal steps"*. Excel's chart flow is the **opposite** of
minimal — select a range, open a gallery of 40 thumbnails, pick, then fight the
axes. Copying it would break the core principle.

### The resolution: suggest first, refine second

**`ChartStack.tsx` already does the hard half of this.** `lib/charts.ts`
inspects the selected data and infers appropriate charts — time on the x-axis
gives a line, categories give a bar, and it refuses to put two different units
on one axis. Extend that rather than adding a chart wizard.

### How it should look and behave

**The suggestion strip.** With data on screen, show 2–4 ready-made chart cards,
each already rendered with the user's actual numbers and a one-line reason:
*"Prices over time"*, *"Compare by area"*. The user clicks one to keep it. They
never see an empty chart to configure.

**Editing, when they want it.** A pencil on each chart opens a panel with
exactly four controls:

| Control | Options |
| --- | --- |
| Chart type | Three big icon buttons: bar · line · pie |
| Bottom of the chart | Dropdown of valid columns |
| What's measured | Dropdown of valid columns |
| Colour | Six swatches |

Everything else — gridlines, legend position, axis bounds — lives behind
**More options**, collapsed. Four controls covers what non-technical users
actually change; the fifth is where a chart editor starts becoming Excel.

**Switching type never loses work.** Changing bar→line keeps the same columns.

### The pie chart problem

Pie charts are the most-requested and most-misused chart there is. Guard rails
rather than a ban:

- Offer pie **only** when there are ≤6 categories that sum to a meaningful
  whole (shares of an area, split of a total).
- With more than 6, offer it but auto-group the tail into "Other".
- Never offer pie for a time series. If someone forces it, show a quiet inline
  note: *"A line chart usually shows change over time more clearly."* Suggest,
  do not block.

### Technical & design considerations

- Store charts as **specs, not images** — `{type, x, y, color, title}` — so they
  save with the project, re-render on new data, and export cleanly.
- Charts must read from the same filtered view as the table. One data path, or
  they will eventually disagree and nobody will know which is right.
- Every chart needs **PNG** and **copy-the-numbers** export. People put these in
  reports and emails; that is the whole point of making them.
- Cap automatic suggestions at four. The failure mode of auto-generation is
  twelve charts nobody reads.

---

## 4. Data layers — property, construction & industry, commodities

### How it should look

**Two levels of hierarchy, never three.** A layer *tree* is what makes ArcGIS
unusable for beginners.

- **Level 1** — three big domain cards in a panel: Property, Construction &
  Industry, Commodity Trading. Each with an icon, a plain-language name and a
  one-line description.
- **Level 2** — inside the active domain, 3–6 named **views**, not a checkbox
  tree: "Sale prices", "Price change", "Property age".

### Visual distinctness without visual mud

Colour alone is not enough — it fails for colour-blind users and at low
contrast. **Give each domain both a hue family and a different mark type:**

| Domain | Colour family | Mark | Why |
| --- | --- | --- | --- |
| Property | Blues | Filled polygons | Parcels genuinely are areas |
| Construction & industry | Ambers | Pins with status rings | Sites are points with a state |
| Commodity trading | Teals | Curved flow lines, width = volume | Flows are relationships, not places |

The mark type carries the meaning even in greyscale.

### How it should behave

**One domain active at a time by default.** Three overlapping datasets on one
map is unreadable — this is the single biggest visual risk in the brief.
Domain cards behave like radio buttons.

For the genuine cross-domain question ("is construction pushing prices up?"),
provide an explicit **Compare** mode that allows exactly two domains and
automatically drops both to outline-only styling.

**The legend is always visible** and shows only what is currently on, near the
map, not in a separate panel. If a legend can be closed, users will close it and
then not know what the colours mean.

### Technical & design considerations

- These three domains have **genuinely different data shapes** — polygons,
  time-stamped points, and origin→destination flows. That is three rendering
  strategies (fill, symbol, line) and three query patterns. Do not design a
  single generic "layer" abstraction that pretends otherwise; it will leak.
- Commodity flows need aggregation at low zoom or the map becomes spaghetti.
  Bundle flows by region below a zoom threshold.
- Every layer needs the provenance treatment `Provenance.tsx` already gives
  factors: source, licence, last updated. Property and commodity data will come
  from commercial feeds with real licence restrictions.
- Point layers need clustering (construction sites cluster heavily in cities).
  Clusters must be clickable to expand, never a dead end.

---

## 5. Zoomable map with progressive detail

### Do not build this

Progressive detail by zoom is what vector tile basemaps already do, extremely
well, and it took the industry fifteen years to get right. Label collision
alone is a hard problem.

`MapCanvas.tsx` already uses **MapLibre GL**, which handles this natively. The
work is choosing a tile source and styling it, not implementing zoom logic.

### The zoom ladder

| Zoom | What appears | Feel |
| --- | --- | --- |
| 0–4 | Countries, major water | "Where in the world" |
| 5–6 | Regions, counties, largest cities | "Which part of the country" |
| 7–9 | Towns, motorways, A-roads | "Which area" |
| 10–12 | Streets, districts, rail | "Which neighbourhood" |
| 13+ | Buildings, POIs, addresses | "Which building" |

Data layers should follow the same discipline: property parcels are meaningless
at zoom 5, so show a choropleth by region there and switch to individual parcels
at zoom 12. **Aggregate at low zoom, detail at high zoom** — same principle,
applied to your data rather than the basemap.

### How it should behave

Three rules that matter for non-technical users specifically:

1. **Always show visible +/− buttons.** Many people do not know scroll-to-zoom
   exists, and trackpad pinch is inconsistent. The buttons are not redundant.
2. **Never let them get lost.** Show the current place name at the map centre
   ("Warwickshire, England") and provide a permanent **Reset view** control.
   The demo already has a fit-to-country button for exactly this reason.
3. **Zoom toward the cursor**, not the screen centre — anything else feels
   broken, even to people who could not say why.

### Technical & design considerations

- **Tile source choice is a real cost decision.** Mapbox and MapTiler bill per
  tile request, and a map-first app makes a lot of requests. **Protomaps** is
  worth serious evaluation: the entire planet is one `.pmtiles` file you host
  yourself, with no per-request billing. For a student project that becomes a
  business, that difference is significant.
- Style the basemap **desaturated and dim** so your data reads as the
  foreground. `MapCanvas.tsx` already does this (`raster-saturation: -0.7`).
- **Never let the basemap block your data.** A hard-won lesson already in the
  code: MapLibre will not paint *any* layer while the style is unloaded, so a
  slow or blocked tile host renders the whole map blank. The initial style now
  contains no external sources and the basemap is added afterwards.
- Mobile: one-finger drag pans, two-finger pinch zooms — and drawing must
  disable pan, or every attempt to draw moves the map instead.

---

## 6. UI philosophy — simple but not toy-like

### Concrete rules, not adjectives

**Language**
- Every button is a verb: "Create project", not "New".
- Ban the jargon list outright: AOI → *area*, raster → *map layer*, attribute
  table → *results*, geometry → *shape*, layer opacity → *see-through*.
- Target roughly a Year 9 reading age in UI copy. Test it.
- Errors say what happened and what to do: *"That area is bigger than we can
  check at once. Try drawing something smaller."* — which is what
  `routes_catalog.py` already returns.

**Interaction**
- One primary action per screen. Exactly one filled button; everything else
  outlined or plain.
- Touch targets ≥44 px. Non-negotiable on the map controls.
- No icon-only buttons without a visible label or a permanent tooltip — except
  the universally understood few (+, −, ✕).
- **Undo over confirm**, everywhere it is possible.
- Every state that can be empty needs a designed empty state that tells the
  user what to do next.

### How "simple" avoids looking "toy-like"

This is a real risk and the answer is **restraint, not decoration**:

| Reads as toy | Reads as professional |
| --- | --- |
| Cartoon illustrations, mascots | Real map imagery, real data |
| Bright primaries, rainbow palettes | One accent, disciplined neutrals |
| Shadows everywhere, or depth faked with saturation | A stated layer ramp, shadow only confirming it |
| Emoji as section markers | Typographic hierarchy |
| Bouncy animations | Fast, short transitions (110–260 ms) |

Specific choices already made in `web/src/index.css` that support this:
slate-blue neutrals rather than default grey; warm bone text on cool ground,
taken from the logo's wordmark; a single burnt-orange accent — the logo's frog
— with semantic colour held separate from it; tabular numerals in every data
table; and generous whitespace on the analytical half.

### The layer ramp

Depth is carried by lightness, not by shadow. Six surfaces sit roughly 4 L\*
apart and get lighter as they come forward, so the stack is readable with
shadows disabled entirely:

| Token | Role | Used by |
| --- | --- | --- |
| `--ink-0` | ground | the map |
| `--ink-1` | sunk | inputs, the timeline track, expanded month rows |
| `--ink-2` | surface | the data panel, the timeline bar |
| `--ink-3` | raised | cards, sticky table headers, panel head |
| `--ink-4` | floating | tool rail, popovers, menus |
| `--ink-5` | overlay | modals |

Elevation (`--e1`…`--e4`), the z-index scale (`--z-map`…`--z-modal`) and the
ramp move together: a surface on `--ink-4` takes `--e3` and `--z-float`.
Mixing them is the bug the scale exists to prevent — and one rule comes with
it, since a z-index creates a stacking context and caps every descendant: a
container hosting a popover that escapes its bounds must itself sit at
`--z-pop`.

**The split that makes both possible:** the map is touch-friendly with large
floating controls; the data panel is dense and spreadsheet-like. Simplicity
lives in the *canvas*, information density lives in the *panel*. Trying to make
both the same is what forces the compromise everyone hates.

### The gallery is the front door

Borrowed from Procreate, and the part worth borrowing is not the grid — it is
that you land on *your work*, not on an empty canvas with a file menu. Opening
a card restores the whole working state (boundary, factors, position in time),
so a site is a place you return to rather than a thing you rebuild.

Three consequences follow from that, and each is load-bearing:

- **A project stores more than a boundary.** The pre-gallery `SavedAoi` kept
  only geometry, so reopening one silently dropped your factor selection.
  Anything the gallery promises to restore has to actually be stored.
- **Save updates the open project.** Otherwise a session of saves leaves a
  gallery of near-identical cards and the home screen becomes the mess it was
  meant to replace.
- **The gallery does not gate anything.** A first-run user with nothing saved
  goes straight to the canvas — an empty gallery is a door into an empty room —
  and a permalink always opens the view it describes, because a shared link is
  usually somebody else's and answering it with *your* projects is the wrong
  answer to "someone sent me this".

Thumbnails are the site's own outline, drawn from stored geometry over a faint
graticule. No tiles and no screenshots: a gallery of forty renders instantly
and offline, and sites are told apart the way a map reader tells them apart
anyway — by shape.

---

## 7. Conflicts between simplicity and functionality

The brief asks for these to be flagged. Here are the seven real ones.

### 7.1 Many data layers vs. an uncluttered interface
**Conflict:** three domains with sub-layers each is dozens of choices; showing
them all is a tree nobody can read.
**Resolution:** two-level hierarchy, one active domain at a time, search that
appears only when the list gets long, and templates that make the common
choices for you. This is exactly how `FactorBrowser.tsx` makes 118 factors
approachable — grouped, searchable, capped at 12 selected.

### 7.2 "Like Excel charts" vs. "minimal steps"
**Conflict:** Excel's power comes from configurability; configurability is
steps.
**Resolution:** suggest-then-refine. Automatic charts as the default path, a
four-control editor as the escape hatch, everything else behind *More options*.
Users who want Excel get 80% of it; users who want a chart get one in a click.

### 7.3 Zero jargon vs. not patronising a professional
**Conflict:** a surveyor knows what a hectare is and will not respect an app
that avoids the word.
**Resolution:** **plain label, precise tooltip.** Never dumb down the *number*,
only the *word*. "Area: 1,113 ha" with a tooltip explaining hectares if needed.
Simplifying the data itself is where you lose the expert user for good.

### 7.4 Non-technical users vs. honest uncertainty
**Conflict:** the truthful answer is often "we do not know for this month", and
gaps look like bugs to inexperienced users.
**Resolution:** show uncertainty in *form*, not just words — greyed values, a
data-availability strip, an explicit "No data" rather than a blank. Never
interpolate silently to make the chart look tidy. A user who later discovers
you invented a number will not trust anything else.

### 7.5 Big obvious buttons vs. information density
**Conflict:** 44 px targets and dense tables are incompatible in one layout.
**Resolution:** the canvas/panel split. Large controls on the map, dense rows in
the panel. Two different interaction registers in one product, deliberately.

### 7.6 Onboarding vs. returning users
**Conflict:** a tutorial that helps on day one is an obstacle on day two.
**Resolution:** skippable at every step, never blocking, asked once, and
permanently available under Help.

### 7.7 Three domains vs. one coherent product
**Conflict:** the deepest one. Property, construction and commodity users want
different things, and serving all three shallowly serves none of them.
**Resolution:** build the layer system generically, ship one domain deeply,
and let real usage decide the second.

---

## 8. What I would push back on

- **Commodity trading is a different product.** Flows between places do not fit
  a draw-an-area interface. If it matters commercially, it deserves its own
  view (a flow map with an origin/destination picker), not a third checkbox in
  the same panel.
- **"Zero jargon" cannot be absolute.** Some terms are the actual name of the
  thing, and inventing a friendlier synonym makes documentation and support
  harder. Aim for *no unexplained jargon* instead.
- **Three domains at launch is too much.** Each needs its own data pipeline,
  licence agreement, refresh schedule and support burden. One done properly is
  worth more than three done thinly, especially with a single developer.

---

## 9. Suggested build order

Sequenced so each phase produces something usable, and the riskiest assumption
is tested first.

| Phase | Scope | Why here |
| --- | --- | --- |
| **1** | Projects: model, home page, autosave, thumbnails | Everything else attaches to a project; retrofitting is painful |
| **2** | Real basemap with the zoom ladder; tile source decided | Unblocks every layer, and the cost decision wants making early |
| **3** | Property layer, end to end | Proves the layer system on the domain closest to existing data |
| **4** | Chart editor on top of the existing suggestions | The auto-charts already work; this adds control |
| **5** | Onboarding tour | Deliberately last — a tour of a half-built product has to be rewritten |
| **6** | Second domain | Chosen from how phase 3 is actually used |

Onboarding last is not a deferral. A tour written against a changing interface
gets rewritten every sprint, and writing it at the end forces you to notice
which parts still need explaining — those are the parts to redesign instead.
