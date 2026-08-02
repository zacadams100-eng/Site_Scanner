/* =====================================================================
   Site Scanner — demo engine

   This is a faithful port of the real backend's series.py, running in the
   browser so the demo needs no server. The figures are generated, but the
   *behaviour* is the product's actual behaviour:

     - optical factors go blank in cloudy months rather than being
       interpolated, and carry a valid_fraction that the UI reads;
     - annual products hold their value across the year and are flagged as
       stepped rather than pretending to be monthly;
     - static factors do not move;
     - a site's character is stable, so two nearby shapes behave alike and a
       northern upland reads differently from a southern city;
     - categorical factors are never averaged.

   Anything the real app would refuse to do, this refuses to do too.
   ===================================================================== */

/* ---- catalogue unpacking (positional arrays keep the payload small) ---- */
const K_CAT = 1;
const CAD = ['monthly', 'annual', 'static', '5 years', 'periodic'];

const FACTORS = DATA.factors.map(a => ({
  id: a[0], name: a[1], base: a[2], group: a[3], unit: a[4],
  kind: a[5] === K_CAT ? 'categorical' : 'continuous',
  cadence: CAD[a[6]], lo: a[7], hi: a[8], derived: !!a[9], note: a[10],
}));
const BASES = DATA.bases.map(a => ({
  id: a[0], name: a[1], source: a[2], licence: a[3], url: a[4],
  native: a[5], cadence: a[6], res: a[7], stored: !!a[8],
}));
const F_BY_ID = Object.fromEntries(FACTORS.map(f => [f.id, f]));
const B_BY_ID = Object.fromEntries(BASES.map(b => [b.id, b]));

/* ---- time ---- */
const STEPS = (() => {
  const out = [];
  for (let y = 2011; y <= 2025; y++)
    for (let m = 1; m <= 12; m++) out.push(`${y}-${String(m).padStart(2, '0')}`);
  return out;
})();
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const labelStep = s => `${MONTHS[+s.slice(5) - 1]} ${s.slice(0, 4)}`;

/* ---- deterministic noise ---- */
function hash(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  // Final avalanche, so neighbouring keys do not produce neighbouring values.
  h ^= h >>> 15; h = Math.imul(h, 2246822507) >>> 0;
  h ^= h >>> 13; h = Math.imul(h, 3266489909) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/* Cloud-limited bases. ESA WorldCover is deliberately absent: it is an annual
   composite built from a full year of imagery, so it has no monthly cloud
   gaps. Treating it as cloud-limited put holes in a product that has none —
   a real bug the Python test suite caught. */
const CLOUDY = new Set(['sentinel2_sr', 'modis_lst']);
const GAP_THRESHOLD = 0.15;

const SEASON_PEAK = {
  Vegetation: 7, Temperature: 7.5, Water: 0.5,
  'Air quality': 1, Radar: 7, 'Night lights': 0,
};
const SEASON_AMP = {
  Vegetation: .34, Temperature: .40, Water: .28, 'Air quality': .22,
  Radar: .12, 'Night lights': .30, 'People & economy': .03,
};

function siteCharacter(lng, lat) {
  const k = `${lng.toFixed(3)}|${lat.toFixed(3)}`;
  const northness = Math.max(0, Math.min(1, (lat - 49.9) / (55.8 - 49.9)));
  return {
    urbanity: hash('u' + k),
    wetness: 0.35 + 0.5 * hash('w' + k) + 0.15 * northness,
    elevation: Math.pow(hash('e' + k), 1.6),
    northness,
    affluence: hash('a' + k),
  };
}

function coherent(group, s) {
  switch (group) {
    case 'Temperature': return 0.75 - 0.45 * s.northness + 0.2 * s.urbanity;
    case 'Water': case 'Flood & water': return 0.25 + 0.55 * s.wetness - 0.3 * s.elevation;
    case 'Terrain': return s.elevation;
    case 'People & economy': return 0.2 + 0.6 * s.affluence;
    case 'Air quality': case 'Built environment': case 'Night lights':
      return 0.1 + 0.8 * s.urbanity;
    case 'Vegetation': case 'Land cover': case 'Designations':
      return 0.8 - 0.55 * s.urbanity;
    default: return 0.5;
  }
}

const URBAN_LED = new Set(['lc_built_pct','impervious_pct','built_pct','building_density',
  'road_density','population_density','no2','nightlight_radiance']);
const GREEN_LED = new Set(['lc_tree_pct','lc_crop_pct','lc_grass_pct','ndvi','evi']);

function baseline(f, s, areaHa) {
  const span = f.hi - f.lo;
  let pos = 0.35 * hash(`b${f.id}${s.urbanity.toFixed(4)}${s.northness.toFixed(4)}`)
          + 0.65 * coherent(f.group, s);
  if (URBAN_LED.has(f.id)) pos = Math.min(1, 0.15 + 0.85 * s.urbanity);
  else if (GREEN_LED.has(f.id)) pos = Math.max(0, 0.85 - 0.6 * s.urbanity) * (0.7 + 0.6 * pos);

  // Large areas regress toward the middle because they average over more
  // varied ground. Real, and it matters to anyone comparing a field with a
  // county.
  const pull = Math.min(1, areaHa / 20000);
  pos = pos * (1 - 0.45 * pull) + 0.5 * (0.45 * pull);
  return f.lo + span * Math.max(0, Math.min(1, pos));
}

function trendPerYear(f, s) {
  const jitter = (hash('t' + f.id + s.urbanity.toFixed(3)) - 0.5) * 0.004;
  if (f.group === 'Temperature') return 0.006 + jitter;
  if (f.id === 'frost_days') return -0.008 + jitter;
  if (['lc_built_pct','built_pct','impervious_pct','building_density'].includes(f.id))
    return 0.004 * (0.3 + s.urbanity) + jitter;
  if (['avg_sale_price','price_per_m2'].includes(f.id)) return 0.021 + jitter;
  if (['no2','pm25','pm10','so2'].includes(f.id)) return -0.010 + jitter;  // genuinely improved
  if (['lc_tree_pct','ancient_woodland_pct'].includes(f.id)) return 0.001 + jitter;
  if (['lc_crop_pct','lc_grass_pct'].includes(f.id)) return -0.002 + jitter;
  return jitter;
}

function seasonal(f, month) {
  const amp = SEASON_AMP[f.group] || 0;
  if (!amp) return 0;
  const peak = SEASON_PEAK[f.group] ?? 7;
  const swing = Math.cos((month - peak) / 12 * 2 * Math.PI);
  if (f.id === 'frost_days') return -amp * swing * 1.6;
  if (['dry_days','sunshine_hours','o3','solar_ghi'].includes(f.id)) return -amp * swing;
  if (f.id === 'growing_degree_days') return amp * Math.max(0, swing) * 1.8;
  return amp * swing;
}

function validFraction(f, year, month, s) {
  if (!CLOUDY.has(f.base)) return 1;
  const clear = 0.5 + 0.42 * Math.cos((month - 7) / 12 * 2 * Math.PI);
  const n = hash(`c${f.base}${year}${month}${s.wetness.toFixed(3)}`);
  return Math.max(0, Math.min(1, clear * (0.55 + 0.75 * n) - 0.12 * s.wetness));
}

function categoricalValue(f, year, s) {
  const classes = DATA.classes[f.id] || ['Unknown'];
  let weights;
  if (f.id === 'lc_dominant') {
    const u = s.urbanity;
    weights = [Math.max(.02, .9 - u), .12, Math.max(.05, .7 - .4 * u),
               Math.max(.05, .8 - .6 * u), .1 + 1.4 * u, .05, .08, .05];
  } else weights = classes.map(() => 1);
  const total = weights.reduce((a, b) => a + b, 0);
  let r = hash(`k${f.id}${s.urbanity.toFixed(3)}${s.northness.toFixed(3)}${Math.floor(year / 5)}`) * total;
  for (let i = 0; i < classes.length; i++) { r -= weights[i]; if (r <= 0) return classes[i]; }
  return classes[classes.length - 1];
}

/** A full monthly series for one factor over one area. */
function generateSeries(factorId, centroid, areaHa) {
  const f = F_BY_ID[factorId];
  const [lng, lat] = centroid;
  const s = siteCharacter(lng, lat);
  const stepped = ['annual', '5 years', 'periodic'].includes(f.cadence);
  const points = [];

  if (f.kind === 'categorical') {
    for (const t of STEPS) {
      const year = +t.slice(0, 4), month = +t.slice(5);
      points.push({
        t, value: categoricalValue(f, year, s),
        valid: validFraction(f, year, month, s),
        interp: stepped && month !== 1,
      });
    }
    return { id: f.id, f, points, annual: rollup(points, f) };
  }

  const base = baseline(f, s, areaHa);
  const span = f.hi - f.lo;
  const trend = trendPerYear(f, s);

  for (const t of STEPS) {
    const year = +t.slice(0, 4), month = +t.slice(5);
    let value, valid, interp = false;

    if (f.cadence === 'static') { value = base; valid = 1; }
    else {
      const sm = stepped ? 1 : month;
      const sy = f.cadence === '5 years' ? year - (year % 5) : year;
      const drift = trend * (sy - 2011) * span;
      const seas = seasonal(f, sm) * span;
      const wob = (hash(`v${f.id}${sy}${sm}${lng.toFixed(3)}${lat.toFixed(3)}`) - 0.5) * 0.09 * span;
      value = base + drift + seas + wob;
      valid = validFraction(f, year, month, s);
      interp = stepped && month !== 1;
    }

    value = Math.max(f.lo, Math.min(f.hi, value));

    // The honest gap. Never interpolated, never guessed.
    if (valid < GAP_THRESHOLD) { points.push({ t, value: null, valid, interp: false }); continue; }
    points.push({ t, value: +value.toFixed(4), valid: +valid.toFixed(3), interp });
  }
  return { id: f.id, f, points, annual: rollup(points, f) };
}

/** Collapse to one row per year — the attribute table's default view. */
function rollup(points, f) {
  const byYear = new Map();
  for (const p of points) {
    const y = +p.t.slice(0, 4);
    if (!byYear.has(y)) byYear.set(y, []);
    byYear.get(y).push(p);
  }
  const rows = [];
  for (const [year, pts] of [...byYear].sort((a, b) => a[0] - b[0])) {
    const good = pts.filter(p => p.value !== null);
    if (!good.length) {
      rows.push({ year, value: null, min: null, max: null, obs: 0, total: pts.length, conf: 0 });
      continue;
    }
    if (f.kind === 'categorical') {
      const counts = {};
      for (const p of good) counts[p.value] = (counts[p.value] || 0) + 1;
      const modal = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
      rows.push({ year, value: modal, min: null, max: null, obs: good.length,
                  total: pts.length, conf: good.reduce((a, p) => a + p.valid, 0) / good.length });
      continue;
    }
    // Weighted by valid fraction: a month where 90% of pixels were clear
    // counts for more than one where 20% were.
    const w = good.map(p => Math.max(0.01, p.valid));
    const sw = w.reduce((a, b) => a + b, 0);
    const mean = good.reduce((a, p, i) => a + p.value * w[i], 0) / sw;
    const vals = good.map(p => p.value);
    rows.push({
      year, value: +mean.toFixed(4),
      min: +Math.min(...vals).toFixed(4), max: +Math.max(...vals).toFixed(4),
      obs: good.length, total: pts.length, conf: sw / w.length,
    });
  }
  return rows;
}

/* ---- geometry ---- */
const R = 6378137;
function ringAreaM2(ring) {
  let total = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[i + 1];
    total += (x2 - x1) * Math.PI / 180 *
      (2 + Math.sin(y1 * Math.PI / 180) + Math.sin(y2 * Math.PI / 180));
  }
  return Math.abs(total * R * R / 2);
}
function polygonAreaHa(ring) {
  const closed = ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]
    ? ring : [...ring, ring[0]];
  return ringAreaM2(closed) / 10000;
}
function centroidOf(ring) {
  const n = ring.length;
  return [ring.reduce((a, p) => a + p[0], 0) / n, ring.reduce((a, p) => a + p[1], 0) / n];
}
function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
/** Douglas–Peucker. A two-second freehand scribble is several hundred
 *  vertices; simplifying on release keeps everything downstream fast. */
function simplify(pts, tol) {
  if (pts.length < 3) return pts;
  const sq = t => t * t;
  const segDist = (p, a, b) => {
    let x = a[0], y = a[1], dx = b[0] - x, dy = b[1] - y;
    if (dx || dy) {
      const t = ((p[0] - x) * dx + (p[1] - y) * dy) / (dx * dx + dy * dy);
      if (t > 1) { x = b[0]; y = b[1]; } else if (t > 0) { x += dx * t; y += dy * t; }
    }
    return sq(p[0] - x) + sq(p[1] - y);
  };
  const run = (first, last, out) => {
    let maxD = tol * tol, idx = 0;
    for (let i = first + 1; i < last; i++) {
      const d = segDist(pts[i], pts[first], pts[last]);
      if (d > maxD) { idx = i; maxD = d; }
    }
    if (idx) { if (idx - first > 1) run(first, idx, out); out.push(pts[idx]); if (last - idx > 1) run(idx, last, out); }
  };
  const out = [pts[0]];
  run(0, pts.length - 1, out);
  out.push(pts[pts.length - 1]);
  return out;
}
