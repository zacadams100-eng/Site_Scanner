# Interactive demo

One self-contained HTML file. No server, no network, no build step at runtime —
open `site-scanner-demo.html` from a `file://` URL and it works.

It exists so the product can be shown and argued about before the data layer is
live. What it demonstrates is real: the drawing tools, the timeline, the
automatic table and charts, comparison, templates, exports and permalinks all
behave exactly as the React app does.

**The figures are generated.** The page says so in the header and every export
carries the same note. What is *not* generated is the behaviour:

- optical factors return **no value** in cloudy months rather than an
  interpolated guess, and carry a `valid_fraction` the UI reads;
- annual products hold their value across the year and are flagged as stepped;
- static factors do not move;
- categorical factors are never averaged;
- a site's character is stable, so two nearby shapes behave alike and a northern
  upland reads differently from a southern city.

Anything the real app would refuse to do, the demo refuses to do too. That is
the point — a demo that quietly interpolates its gaps teaches the wrong thing
about the product.

## Rebuilding

```sh
./build.sh
```

`catalog.data.js` is generated from the real `catalog.py`, so the demo's 118
factors and 20 base datasets cannot drift from the product's:

```sh
python3 - <<'PY'
import json, catalog
from bench.england import ENGLAND_OUTLINE
factors = [[f["id"], f["name"], f["base"], f["group"], f["unit"],
            1 if f["kind"] == "categorical" else 0,
            {"monthly":0,"annual":1,"static":2,"5 years":3,"periodic":4}[f["cadence"]],
            f["lo"], f["hi"], 1 if f["derived"] else 0, f["note"]]
           for f in catalog.FACTORS]
bases = [[b["id"], b["name"], b["source"], b["licence"], b["url"],
          b["native_cadence"], b["cadence"], b["resolution_m"],
          1 if b["stored"] else 0] for b in catalog.BASES]
out = {"factors": factors, "bases": bases, "groups": catalog.GROUPS,
       "classes": catalog.CLASS_VALUES,
       "outline": [[round(x,4), round(y,4)] for x, y in ENGLAND_OUTLINE],
       "summary": catalog.catalogue_summary()}
open("demo/catalog.data.js","w").write("const DATA=" + json.dumps(out, separators=(",",":")) + ";")
PY
```

Positional arrays rather than objects: 118 factors as objects is ~34 KB of
repeated key names, and under 12 KB this way.

## Files

| File | What it is |
| --- | --- |
| `demo-head.html` | Design tokens and all CSS, including both themes |
| `demo-body.html` | Markup |
| `catalog.data.js` | Generated catalogue + England outline |
| `demo-engine.js` | Port of `series.py` — the generator and its geometry helpers |
| `demo-ui.js` | State, projection, map rendering, drawing tools, URL state |
| `demo-render.js` | Table, chart inference, SVG charts, sources, sparkline |
| `demo-wire.js` | Event wiring, factor browser, templates, menus, exports |

## Known limits

- **No basemap.** A self-contained file cannot fetch tiles, so the map shows a
  simplified England outline and an adaptive graticule rather than imagery.
  Inventing fake roads and towns would look better and be dishonest.
- **The England outline is ~50 vertices.** Fine for drawing and for framing;
  not a substitute for OS Boundary-Line.
- **Cells are a square grid, not H3.** The real fast tier uses H3 at two
  resolutions (see `BENCHMARK.md`); the demo approximates it with a clipped
  square grid, which behaves the same way from the UI's point of view.
