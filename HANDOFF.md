# Handoff — Contour desk study map

Branch: `claude/laughing-pascal-bbmwv9`
Repo: `zacadams100-eng/Site_Scanner` (public)

## What changed in this session

Site Scanner (satellite statistics, Earth Engine) was replaced by the
contour-sheet tool: red line in, A4 PDF + GeoPackage + JSON record out, from
30 official designation and constraint layers. The React map app in `web/`
was kept and rebuilt around it:

- draw or upload the red line
- make the sheet
- every finding drawn on the map in the PDF's colours, with 1 km and 2 km rings
- the findings schedule in the panel, using the PDF's wording
- downloads
- a basemap switch: Esri satellite (default), satellite + labels, topographic,
  OpenStreetMap, light grey

The satellite code is in history up to `5e4e012`.

## State of play

- 13 Python tests pass and 4 frontend tests pass. The app builds and was driven
  end to end in a headless browser on fixture data.
- **No live publisher query has been run yet.** Every workspace this was built
  in blocked planning.data.gov.uk, the ArcGIS hosts and environment.data.gov.uk.
  The CI job **Live sheet** is the first real run. Read its warnings and
  artifacts before trusting any layer.
- The basemap tiles were requested correctly but could not load in the sandbox.
  They have not been seen rendering yet.

## Rules, from the product notes (24 Oct 2026)

Until a consultancy has paid twice, do not add:

- habitat, coastal or scenario scanners, Earth Engine or satellite indices
- a self-serve app, customer logins or subscriptions
- the draw page on the internet (it has no login)
- more layers, unless a client asks for a specific one
- a rebrand or a new website direction

The website and order flow live elsewhere (LASSO repo, currently empty; the
site itself runs in Cloud Shell). The payment link is parked for now.

## Working style

The user is a university student, not a professional developer. Explain fixes
plainly, give the exact command, say what success looks like. Verify by running
things. Screenshots are the highest-signal input.
