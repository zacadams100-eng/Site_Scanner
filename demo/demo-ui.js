/* =====================================================================
   Site Scanner — UI
   ===================================================================== */

const $ = s => document.querySelector(s);
const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const TEMPLATES = [
  { id:'veg',    name:'Vegetation change', blurb:'Is this land getting greener or browner over 15 years?', tool:'free',   factors:['ndvi','lc_tree_pct','lc_grass_pct','precip_total'] },
  { id:'flood',  name:'Flood exposure',    blurb:'How exposed is this site to water, and is that changing?', tool:'rect', factors:['flood_zone3_pct','hand','water_occurrence','max_daily_precip'] },
  { id:'urban',  name:'Urban growth',      blurb:'How fast is this area being built on?',                 tool:'rect',   factors:['lc_built_pct','built_volume','population_density','nightlight_radiance'] },
  { id:'solar',  name:'Solar suitability', blurb:'Would a solar array work here?',                        tool:'circle', factors:['solar_ghi','slope_mean','solar_aspect_score','lc_built_pct'] },
  { id:'heat',   name:'Urban heat',        blurb:'How much hotter is this area than its surroundings?',   tool:'rect',   factors:['lst_day','heat_anomaly','lc_tree_pct','impervious_pct'] },
  { id:'crop',   name:'Crop performance',  blurb:'How has this field performed season by season?',        tool:'free',   factors:['ndvi','soil_organic_carbon','soil_moisture','growing_degree_days'] },
];

const S = {
  aoi: null, tool: null, series: {}, cells: [],
  selected: ['ndvi', 'lc_tree_pct', 'precip_total', 'lst_day'],
  t: STEPS.indexOf('2025-07'), compare: null, playing: false,
  tab: 'table', expanded: new Set(), sort: { col: 'year', asc: true },
  past: [], future: [], saved: [], areaHa: 0, centroid: null,
  menu: null, flash: null,
};
const MAX_FACTORS = 12;

/* ---------- projection: equirectangular with a latitude correction, so
     England is not stretched sideways. ---------- */
const VIEW = { w: 0, h: 0, scale: 1, cx: 0, cy: 0 };
const LAT0 = 53.0;
const KX = Math.cos(LAT0 * Math.PI / 180);

let viewInit = false;   // cleared by the fit-to-UK control
function fitView(w, h) {
  VIEW.w = w; VIEW.h = h;
  if (viewInit) return;            // resizing must not throw away the user's zoom
  // Frame the whole UK on first paint, so the opening view answers "where is
  // this" before anything else.
  const all = [DATA.outline, ...DATA.context.map(c => c[1])].flat();
  const xs = all.map(p => p[0] * KX), ys = all.map(p => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  VIEW.scale = Math.min(w / (x1 - x0), h / (y1 - y0)) * 0.92;
  VIEW.cx = (x0 + x1) / 2; VIEW.cy = (y0 + y1) / 2;
  viewInit = true;
}

/** Frame a shape with room around it, so a loaded or restored AOI is visible
 *  rather than filling the whole canvas edge to edge. */
function frameRing(ring) {
  const xs = ring.map(p => p[0] * KX), ys = ring.map(p => p[1]);
  const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
  VIEW.cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  VIEW.cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  VIEW.scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE,
    Math.min(VIEW.w / (w || 1e-4), VIEW.h / (h || 1e-4)) * 0.3));
}
const MIN_SCALE = 40, MAX_SCALE = 40000;
function zoomAt(px, py, factor) {
  const before = toLngLat(px, py);
  VIEW.scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, VIEW.scale * factor));
  const after = toLngLat(px, py);
  // Keep the point under the cursor fixed, which is what makes wheel zoom
  // feel like a map rather than a slider.
  VIEW.cx += (before[0] - after[0]) * KX;
  VIEW.cy += before[1] - after[1];
  drawMap();
}
function panBy(dx, dy) {
  VIEW.cx -= dx / VIEW.scale;
  VIEW.cy += dy / VIEW.scale;
  drawMap();
}

const toPx = ([lng, lat]) => [
  VIEW.w / 2 + (lng * KX - VIEW.cx) * VIEW.scale,
  VIEW.h / 2 - (lat - VIEW.cy) * VIEW.scale,
];
const toLngLat = (px, py) => [
  (VIEW.cx + (px - VIEW.w / 2) / VIEW.scale) / KX,
  VIEW.cy - (py - VIEW.h / 2) / VIEW.scale,
];

/* ---------- colour ---------- */
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
/* One ramp, matching the product's (web/src/lib/format.ts): it starts near the
   page so a low value recedes into it and runs through moss to a deep
   instrument blue. Lightness falls all the way along, so the ordering survives
   greyscale printing and colour-blind reading. */
const RAMP = [[246,243,235],[214,220,200],[166,189,158],[109,150,126],[56,111,116],[23,71,97]];
function ramp(t, alpha = 1) {
  const R_ = RAMP;
  const x = Math.max(0, Math.min(0.999, t)) * (R_.length - 1);
  const i = Math.floor(x), fr = x - i;
  const a = R_[i], b = R_[Math.min(R_.length - 1, i + 1)];
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * fr));
  return `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
}
/* Coral leads so the primary series matches the accent and the scrubber; the
   rest fan out in hue and stay distinguishable against navy. */
/* Matches the product's series palette (web/src/lib/format.ts): moss leads,
   because the first series is the one drawn on the map. */
const SERIES_COLORS = ['#4d6048','#1f88b4','#a8722c','#7b5ea7','#2f7d6b','#b4534f','#5d7f2f','#8a5a78','#3f6b96','#96742f','#547a5c','#7a4f3a'];
const sColor = i => SERIES_COLORS[i % SERIES_COLORS.length];

/** A hex token at a given alpha. Lets the canvas honour the theme's accent
 *  instead of repeating literal colours that then drift out of step. */
function color(hex, alpha) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

/* ---------- formatting ---------- */
function fmt(v, f) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string') return v;
  if (!isFinite(v)) return '—';
  const u = f ? f.unit : '';
  if (u === '£' || u === '£/m²') return '£' + Math.round(v).toLocaleString('en-GB');
  if (u === '%') return v.toFixed(1) + '%';
  if (u === '°' || u === '°C') return v.toFixed(1);
  if (u === 'm' || u === 'mm') return Math.abs(v) >= 100 ? Math.round(v).toLocaleString('en-GB') : v.toFixed(1);
  if (['days','sales','cells'].includes(u)) return Math.round(v).toLocaleString('en-GB');
  if (Math.abs(v) >= 10000) return Math.round(v).toLocaleString('en-GB');
  if (Math.abs(v) >= 100) return v.toFixed(1);
  return v.toFixed(2);
}
const compact = v => v === null ? '—' : typeof v === 'string' ? v
  : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'M'
  : Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(1) + 'k'
  : Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(2);
const fmtArea = ha => ha >= 10000 ? (ha / 100).toFixed(0) + ' km²'
  : ha >= 100 ? Math.round(ha).toLocaleString('en-GB') + ' ha' : ha.toFixed(1) + ' ha';
const band = c => c >= 0.7 ? '' : c >= 0.4 ? 'c-fair' : 'c-poor';

/* ---------- map ---------- */
const mapCv = $('#map'), mapCtx = mapCv.getContext('2d');
let draft = null;

function sizeMap() {
  const r = mapCv.parentElement.getBoundingClientRect();
  const dpr = devicePixelRatio || 1;
  mapCv.width = r.width * dpr; mapCv.height = r.height * dpr;
  mapCv.style.width = r.width + 'px'; mapCv.style.height = r.height + 'px';
  mapCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  fitView(r.width, r.height);
  drawMap();
  drawSpark();
}

function drawMap() {
  const { w, h } = VIEW;
  mapCtx.clearRect(0, 0, w, h);
  mapCtx.fillStyle = cssVar('--sea'); mapCtx.fillRect(0, 0, w, h);

  // Graticule. Real coordinate lines that subdivide as you zoom, so the map
  // keeps a sense of scale rather than becoming a flat expanse when you are in
  // close on a single field.
  const degPerPx = 1 / VIEW.scale;
  const stepDeg = [2, 1, .5, .25, .1, .05, .02, .01, .005, .002, .001]
    .find(d => d / degPerPx > 55) ?? .001;
  mapCtx.strokeStyle = 'rgba(35,35,35,.10)';
  mapCtx.lineWidth = 1;
  const tl = toLngLat(0, 0), br = toLngLat(w, h);
  for (let lat = Math.floor(br[1] / stepDeg) * stepDeg; lat <= tl[1]; lat += stepDeg) {
    const y = toPx([0, lat])[1];
    mapCtx.beginPath(); mapCtx.moveTo(0, y); mapCtx.lineTo(w, y); mapCtx.stroke();
  }
  for (let lng = Math.floor(tl[0] / stepDeg) * stepDeg; lng <= br[0]; lng += stepDeg) {
    const x = toPx([lng, 0])[0];
    mapCtx.beginPath(); mapCtx.moveTo(x, 0); mapCtx.lineTo(x, h); mapCtx.stroke();
  }

  // Landmasses. Everything outside England is drawn first and dimmed — it is
  // context, not coverage, and the difference has to be visible at a glance so
  // nobody draws a shape over Wales and wonders why it is refused.
  const landPath = (ring) => {
    mapCtx.beginPath();
    ring.forEach((p, i) => { const [x, y] = toPx(p); i ? mapCtx.lineTo(x, y) : mapCtx.moveTo(x, y); });
    mapCtx.closePath();
  };

  mapCtx.fillStyle = cssVar('--outside-fill');
  mapCtx.strokeStyle = cssVar('--outside-line');
  mapCtx.lineWidth = 1;
  for (const [, ring] of DATA.context) { landPath(ring); mapCtx.fill(); mapCtx.stroke(); }

  landPath(DATA.outline);
  mapCtx.fillStyle = cssVar('--land-fill'); mapCtx.fill();
  mapCtx.strokeStyle = cssVar('--land-line'); mapCtx.lineWidth = 1.4; mapCtx.stroke();

  // Name the context landmasses, but only when zoomed out far enough that the
  // labels are answering "where am I" rather than cluttering a field view.
  if (VIEW.scale < 700) {
    mapCtx.font = `500 10px ${cssVar('--ui') || 'system-ui'}`;
    mapCtx.fillStyle = cssVar('--ink-3');
    mapCtx.textAlign = 'center';
    for (const [name, ring] of DATA.context) {
      const xs = ring.map(p => p[0]), ys = ring.map(p => p[1]);
      const [cx, cy] = toPx([(Math.min(...xs) + Math.max(...xs)) / 2,
                             (Math.min(...ys) + Math.max(...ys)) / 2]);
      if (cx < -40 || cx > w + 40 || cy < -20 || cy > h + 20) continue;
      mapCtx.fillText(name, cx, cy);
    }
    mapCtx.textAlign = 'start';
  }

  // Cell grid, coloured at the current timestep. The cells and their offsets
  // were computed once when the shape was drawn, so scrubbing repaints from
  // memory and never recomputes — this is the client-side shape of the H3
  // fast tier.
  const primary = S.selected[0];
  const ser = S.series[primary];
  if (S.cells.length && ser && ser.f.kind === 'continuous') {
    const p = ser.points[S.t];
    if (p && p.value !== null) {
      const spread = (ser.f.hi - ser.f.lo) * 0.16;
      for (const c of S.cells) {
        const v = p.value + c.o * spread;
        const t = (v - ser.f.lo) / (ser.f.hi - ser.f.lo);
        const [x0, y0] = toPx([c.b[0], c.b[3]]);
        const [x1, y1] = toPx([c.b[2], c.b[1]]);
        mapCtx.fillStyle = ramp(t, 0.82);
        mapCtx.fillRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
      }
    }
  }

  const outline = (ring, stroke, fill, dash) => {
    mapCtx.beginPath();
    ring.forEach((p, i) => { const [x, y] = toPx(p); i ? mapCtx.lineTo(x, y) : mapCtx.moveTo(x, y); });
    mapCtx.closePath();
    if (fill) { mapCtx.fillStyle = fill; mapCtx.fill(); }
    mapCtx.setLineDash(dash || []);
    mapCtx.strokeStyle = stroke; mapCtx.lineWidth = 2; mapCtx.stroke();
    mapCtx.setLineDash([]);
  };
  if (S.aoi) {
    outline(S.aoi, cssVar('--accent'), color(cssVar('--accent'), .07));

    // At national zoom a field is three pixels across and effectively
    // invisible. Ring it so "where am I putting this" is answerable without
    // zooming in and back out again.
    const px = S.aoi.map(toPx);
    const xs = px.map(p => p[0]), ys = px.map(p => p[1]);
    const wpx = Math.max(...xs) - Math.min(...xs);
    const hpx = Math.max(...ys) - Math.min(...ys);
    if (Math.max(wpx, hpx) < 16) {
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
      mapCtx.strokeStyle = cssVar('--accent');
      mapCtx.lineWidth = 1.4;
      mapCtx.beginPath(); mapCtx.arc(cx, cy, 11, 0, 2 * Math.PI); mapCtx.stroke();
      mapCtx.globalAlpha = .55;
      for (const [dx, dy] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
        mapCtx.beginPath();
        mapCtx.moveTo(cx + dx * 14, cy + dy * 14);
        mapCtx.lineTo(cx + dx * 19, cy + dy * 19);
        mapCtx.stroke();
      }
      mapCtx.globalAlpha = 1;
    }
  }
  if (draft) outline(draft, cssVar('--accent-2'), color(cssVar('--accent-2'), .12), [5, 4]);

  // Scale bar, recomputed for the current projection.
  const kmPerPx = 111.32 * KX / VIEW.scale;
  const target = 80 * kmPerPx;
  const nice = [1,2,5,10,20,50,100,200,500].reduce((a, b) => Math.abs(b - target) < Math.abs(a - target) ? b : a);
  $('#scaleBar').style.width = (nice / kmPerPx).toFixed(0) + 'px';
  $('#scaleLabel').textContent = nice + ' km';
}

/* ---------- drawing ---------- */
let drawing = false, start = null, freePts = [];

function setTool(t) {
  S.tool = S.tool === t ? null : t;
  for (const id of ['rect', 'circle', 'free'])
    $('#t-' + id).setAttribute('aria-pressed', String(S.tool === id));
  mapCv.classList.toggle('drawing', !!S.tool);
  $('#hint').textContent = S.tool
    ? { rect: 'Drag across the map to draw a rectangle',
        circle: 'Drag from the centre outward',
        free: 'Drag to trace any shape' }[S.tool]
    : S.aoi ? 'Scrub the timeline, or pick another tool to redraw'
            : 'Pick a tool, then drag on the map';
}

function evPos(e) {
  const r = mapCv.getBoundingClientRect();
  const p = e.touches ? e.touches[0] : e;
  return [p.clientX - r.left, p.clientY - r.top];
}
function rectRing(a, b) { return [a, [b[0], a[1]], b, [a[0], b[1]], a]; }
function circleRing(c, edge) {
  const dx = (edge[0] - c[0]) * KX, dy = edge[1] - c[1];
  const r = Math.hypot(dx, dy);
  const out = [];
  for (let i = 0; i <= 64; i++) {
    const a = i / 64 * 2 * Math.PI;
    out.push([c[0] + (r * Math.cos(a)) / KX, c[1] + r * Math.sin(a)]);
  }
  return out;
}

function onDown(e) {
  if (!S.tool) return;
  e.preventDefault();
  drawing = true;
  start = toLngLat(...evPos(e));
  freePts = [start];
}
function onMove(e) {
  if (!drawing) return;
  e.preventDefault();
  const ll = toLngLat(...evPos(e));
  if (S.tool === 'rect') draft = rectRing(start, ll);
  else if (S.tool === 'circle') draft = circleRing(start, ll);
  else { freePts.push(ll); if (freePts.length > 2) draft = [...freePts, freePts[0]]; }
  drawMap();
}
function onUp(e) {
  if (!drawing) return;
  e.preventDefault();
  drawing = false;
  const ll = e.changedTouches ? toLngLat(...evPos({ touches: e.changedTouches })) : toLngLat(...evPos(e));
  let ring = null;
  if (S.tool === 'rect') { if (Math.abs(start[0] - ll[0]) > 1e-4) ring = rectRing(start, ll); }
  else if (S.tool === 'circle') { if (Math.hypot(start[0] - ll[0], start[1] - ll[1]) > 1e-4) ring = circleRing(start, ll); }
  else if (freePts.length >= 4) {
    const tol = 6 / VIEW.scale;
    const s = simplify(freePts, tol);
    ring = [...s, s[0]];
  }
  draft = null; freePts = [];
  if (ring) setAoi(ring);
  else drawMap();
}

let panning = false, panLast = null;
mapCv.addEventListener('wheel', e => {
  e.preventDefault();
  const r = mapCv.getBoundingClientRect();
  zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.18 : 1 / 1.18);
}, { passive: false });

mapCv.addEventListener('mousedown', e => {
  if (S.tool) return;
  panning = true; panLast = [e.clientX, e.clientY];
  mapCv.style.cursor = 'grabbing';
});
window.addEventListener('mousemove', e => {
  if (!panning) return;
  panBy(e.clientX - panLast[0], e.clientY - panLast[1]);
  panLast = [e.clientX, e.clientY];
});
window.addEventListener('mouseup', () => { panning = false; mapCv.style.cursor = ''; });

mapCv.addEventListener('mousedown', onDown);
window.addEventListener('mousemove', onMove);
window.addEventListener('mouseup', onUp);
mapCv.addEventListener('touchstart', onDown, { passive: false });
window.addEventListener('touchmove', onMove, { passive: false });
window.addEventListener('touchend', onUp, { passive: false });

/* ---------- AOI ---------- */
function setAoi(ring, opts = {}) {
  if (!opts.skipHistory) { S.past.push(S.aoi); if (S.past.length > 40) S.past.shift(); S.future = []; }
  S.aoi = ring;
  S.tool = null; setTool(null);
  if (!ring) { S.series = {}; S.cells = []; S.areaHa = 0; render(); drawMap(); syncUrl(); return; }

  S.areaHa = polygonAreaHa(ring);
  S.centroid = centroidOf(ring);
  if (opts.frame !== false) frameRing(ring);
  buildCells(ring);
  recompute();
  render(); drawMap(); syncUrl();
}

/** A grid of cells clipped to the shape, each with a stable offset — the
 *  miniature of the pre-aggregated tier the real backend serves. */
function buildCells(ring) {
  const xs = ring.map(p => p[0]), ys = ring.map(p => p[1]);
  const w0 = Math.min(...xs), w1 = Math.max(...xs);
  const s0 = Math.min(...ys), s1 = Math.max(...ys);
  const n = 16, dx = (w1 - w0) / n, dy = (s1 - s0) / n;
  S.cells = [];
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const a = w0 + i * dx, b = s0 + j * dy;
    const cx = a + dx / 2, cy = b + dy / 2;
    if (!pointInRing(cx, cy, ring)) continue;
    const k = `${cx.toFixed(5)}|${cy.toFixed(5)}`;
    S.cells.push({ b: [a, b, a + dx, b + dy], o: (0.65 * hash(k) + 0.35 * hash(k + 's')) * 2 - 1 });
  }
}

function recompute() {
  S.series = {};
  for (const id of S.selected) S.series[id] = generateSeries(id, S.centroid, S.areaHa);
}

/* ---------- URL state ---------- */
function encodeRing(ring) {
  let px = 0, py = 0;
  return ring.map(([lng, lat]) => {
    const x = Math.round(lng * 1e5), y = Math.round(lat * 1e5);
    const s = `${x - px}.${y - py}`; px = x; py = y; return s;
  }).join('_');
}
function decodeRing(s) {
  let px = 0, py = 0; const out = [];
  for (const part of s.split('_')) {
    const i = part.indexOf('.', part[0] === '-' ? 1 : 0);
    if (i < 0) continue;
    px += +part.slice(0, i); py += +part.slice(i + 1);
    out.push([px / 1e5, py / 1e5]);
  }
  return out;
}
function syncUrl() {
  const parts = [];
  if (S.aoi) parts.push('g=' + encodeRing(S.aoi));
  parts.push('f=' + S.selected.join('.'), 't=' + S.t);
  if (S.compare !== null) parts.push('c=' + S.compare);
  history.replaceState(null, '', '#' + parts.join('&'));
}
function hydrate() {
  const raw = location.hash.replace(/^#/, '');
  if (!raw) return false;
  let ring = null;
  for (const kv of raw.split('&')) {
    const i = kv.indexOf('='); if (i < 0) continue;
    const k = kv.slice(0, i), v = kv.slice(i + 1);
    if (k === 'g') { const r = decodeRing(v); if (r.length >= 3) ring = r; }
    else if (k === 'f') { const f = v.split('.').filter(x => F_BY_ID[x]); if (f.length) S.selected = f.slice(0, MAX_FACTORS); }
    else if (k === 't') S.t = Math.max(0, Math.min(STEPS.length - 1, +v || 0));
    else if (k === 'c') S.compare = Math.max(0, Math.min(STEPS.length - 1, +v || 0));
  }
  if (ring) { setAoi(ring, { skipHistory: true }); return true; }
  return false;
}
