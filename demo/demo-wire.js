/* =====================================================================
   Site Scanner — wiring
   ===================================================================== */

function flash(msg, isErr) {
  const old = document.querySelector('.flash');
  if (old) old.remove();
  const n = el('div', 'flash' + (isErr ? ' err' : ''), esc(msg));
  document.querySelector('.actions').appendChild(n);
  setTimeout(() => n.remove(), 2600);
}

function render() {
  const body = $('#panelBody');
  body.innerHTML = '';
  $('#facCount').textContent = S.selected.length;
  $('#panelTitle').textContent = S.aoi ? 'Site report' : 'No area drawn';
  $('#panelArea').textContent = S.aoi ? fmtArea(S.areaHa) : '';
  for (const b of ['saveBtn', 'shareBtn', 'exportBtn']) $('#' + b).disabled = !S.aoi;
  $('#clearBtn').disabled = !S.aoi;
  $('#undoBtn').disabled = !S.past.length;
  $('#redoBtn').disabled = !S.future.length;
  for (const t of document.querySelectorAll('.tab'))
    t.setAttribute('aria-selected', String(t.dataset.tab === S.tab));

  if (!S.aoi) {
    body.appendChild(el('div', 'empty-state', `
      <p>Draw a rectangle, circle or freehand shape on England.</p>
      <p class="sub">The attribute table and charts generate themselves — no extra steps.</p>
      <div class="meta">${DATA.summary.factor_count} factors · ${STEPS.length} monthly steps<br>
        ${DATA.summary.stored_base_count} stored datasets · ${DATA.summary.derived_factor_count} derived</div>`));
  } else if (S.tab === 'table') renderTable(body);
  else if (S.tab === 'charts') renderCharts(body);
  else renderSources(body);

  renderReadout();
}

function renderReadout() {
  $('#roStep').textContent = labelStep(STEPS[S.t]);
  $('#range').value = S.t;
  const ser = S.series[S.selected[0]];
  const roVal = $('#roVal'), roFac = $('#roFac');
  if (!ser) { roVal.textContent = ''; roVal.className = 'val'; roFac.textContent = ''; return; }
  const p = ser.points[S.t];
  if (p.value === null) { roVal.textContent = 'No data'; roVal.className = 'val gap'; }
  else {
    roVal.className = 'val';
    roVal.innerHTML = `${compact(p.value)} ${esc(ser.f.unit)}` +
      (p.valid < 0.4 ? ' <span class="lo" title="Few usable pixels this month">low</span>' : '');
  }
  if (S.compare !== null) {
    roFac.innerHTML = `<button class="vs" title="Clear the comparison point">vs ${labelStep(STEPS[S.compare])} ×</button>`;
    roFac.querySelector('.vs').onclick = () => { S.compare = null; render(); drawSpark(); syncUrl(); };
  } else roFac.textContent = ser.f.name;
}

/* ---------- factor browser ---------- */
let browserNode = null, query = '', collapsed = new Set();
function toggleBrowser(open) {
  if (browserNode) { browserNode.remove(); browserNode = null; }
  $('#browserBtn').setAttribute('aria-expanded', String(!!open));
  if (!open) return;
  const n = el('div', 'browser');
  n.innerHTML = `<header>
      <input type="search" placeholder="Search ${DATA.summary.factor_count} factors…" value="${esc(query)}" aria-label="Search factors">
      <button class="x" aria-label="Close">×</button>
    </header>
    <div class="meta">${DATA.summary.factor_count} factors · ${DATA.summary.stored_base_count} stored datasets · ${DATA.summary.derived_factor_count} derived${S.selected.length >= MAX_FACTORS ? ' · <span style="color:var(--warn)">12 selected, remove one to add another</span>' : ''}</div>
    <div class="list"></div>`;
  n.querySelector('.x').onclick = () => toggleBrowser(false);
  const input = n.querySelector('input');
  input.oninput = e => { query = e.target.value; const at = e.target.selectionStart; toggleBrowser(true); const i2 = browserNode.querySelector('input'); i2.focus(); i2.setSelectionRange(at, at); };

  const list = n.querySelector('.list');
  const q = query.trim().toLowerCase();
  const matched = q ? FACTORS.filter(f => (f.name + ' ' + f.group + ' ' + f.note + ' ' + f.unit).toLowerCase().includes(q)) : FACTORS;
  const groups = {};
  for (const f of matched) (groups[f.group] ||= []).push(f);

  if (!Object.keys(groups).length) list.appendChild(el('div', 'menu', `<div class="empty">Nothing matches “${esc(query)}”.</div>`));

  for (const [g, fs] of Object.entries(groups)) {
    const head = el('button', 'grp', `<span class="caret">${collapsed.has(g) ? '▸' : '▾'}</span>${esc(g)}<em>${fs.length}</em>`);
    head.onclick = () => { collapsed.has(g) ? collapsed.delete(g) : collapsed.add(g); toggleBrowser(true); };
    list.appendChild(head);
    if (collapsed.has(g)) continue;
    for (const f of fs) {
      const on = S.selected.includes(f.id);
      const blocked = !on && S.selected.length >= MAX_FACTORS;
      const b = el('button', 'fac',
        `<i>${on ? '✓' : ''}</i><s>${esc(f.name)}</s>` +
        (f.derived ? '<span class="d" title="Derived on read — not stored separately">ƒ</span>' : '') +
        (f.kind === 'categorical' ? '<span class="k" title="Categorical — never averaged">cat</span>' : '') +
        `<u>${esc(f.unit)}</u>`);
      b.setAttribute('aria-pressed', String(on));
      b.disabled = blocked;
      b.title = `${f.note}\nSource: ${B_BY_ID[f.base].name}\nCadence: ${f.cadence}` +
        (f.derived ? '\nDerived — computed from the base, not stored separately' : '');
      b.onclick = () => {
        if (on) { if (S.selected.length === 1) return; S.selected = S.selected.filter(x => x !== f.id); }
        else S.selected = [...S.selected, f.id];
        if (S.aoi) recompute();
        toggleBrowser(true); render(); drawMap(); drawSpark(); syncUrl();
      };
      list.appendChild(b);
    }
  }
  $('#app').appendChild(n);
  browserNode = n;
  if (!q) input.focus();
}

/* ---------- templates ---------- */
function openTemplates() {
  const scrim = el('div', 'scrim');
  scrim.onclick = e => { if (e.target === scrim) scrim.remove(); };
  const sheet = el('div', 'sheet');
  sheet.innerHTML = `<div class="sheet-head">
      <div><h2>Start from a question</h2>
      <p>Each one picks the right factors for you. ${S.aoi ? 'Your drawn shape stays as it is.' : 'Then draw a shape on the map.'}</p></div>
      <button class="x" aria-label="Close">×</button>
    </div><div class="tpl-grid"></div>`;
  sheet.querySelector('.x').onclick = () => scrim.remove();
  const grid = sheet.querySelector('.tpl-grid');
  for (const t of TEMPLATES) {
    const b = el('button', 'tpl',
      `<b>${esc(t.name)}</b><p>${esc(t.blurb)}</p><div class="chips">` +
      t.factors.map(f => `<span class="chip">${esc(F_BY_ID[f].name)}</span>`).join('') + '</div>');
    b.onclick = () => {
      S.selected = t.factors.slice(0, MAX_FACTORS);
      if (S.aoi) recompute();
      scrim.remove();
      setTool(t.tool);
      render(); drawMap(); drawSpark(); syncUrl();
    };
    grid.appendChild(b);
  }
  scrim.appendChild(sheet);
  document.body.appendChild(scrim);
  const onEsc = e => { if (e.key === 'Escape') { scrim.remove(); window.removeEventListener('keydown', onEsc); } };
  window.addEventListener('keydown', onEsc);
}

/* ---------- menus ---------- */
function closeMenus() {
  for (const m of document.querySelectorAll('.menu')) m.remove();
  for (const b of ['sitesBtn', 'exportBtn']) $('#' + b).setAttribute('aria-expanded', 'false');
  S.menu = null;
}
function openMenu(btn, items) {
  const wasOpen = S.menu === btn.id;
  closeMenus();
  if (wasOpen) return;
  const m = el('div', 'menu');
  if (!items.length) m.appendChild(el('div', 'empty', 'Nothing saved yet.'));
  for (const it of items) {
    if (it.row) { m.appendChild(it.row); continue; }
    const b = el('button', null, esc(it.label));
    b.onclick = () => { closeMenus(); it.run(); };
    m.appendChild(b);
  }
  btn.parentElement.appendChild(m);
  btn.setAttribute('aria-expanded', 'true');
  S.menu = btn.id;
}

/* ---------- exports ---------- */
function dl(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
const csvEsc = v => /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v);

function exportAnnual() {
  const cs = cols();
  const lines = [
    `# Site Scanner — demo export, ${new Date().toISOString().slice(0, 10)}`,
    `# Area: ${S.areaHa.toFixed(1)} ha`,
    `# Figures are generated for this demo, not observed`,
    ['Year', ...cs.map(c => `${c.f.name} (${c.f.unit})`)].map(csvEsc).join(','),
  ];
  for (const r0 of cs[0].annual)
    lines.push([r0.year, ...cs.map(c => {
      const r = c.annual.find(a => a.year === r0.year);
      return r && r.value !== null ? r.value : '';
    })].map(csvEsc).join(','));
  dl(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }), 'site-scanner-annual.csv');
  flash('Downloaded');
}
function exportMonthly() {
  const cs = cols();
  const head = ['Month', ...cs.flatMap(c => [`${c.f.name} (${c.f.unit})`, `${c.f.name} valid fraction`])];
  const lines = [head.map(csvEsc).join(',')];
  STEPS.forEach((t, i) => {
    lines.push([t, ...cs.flatMap(c => [c.points[i].value ?? '', c.points[i].valid])].map(csvEsc).join(','));
  });
  dl(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }), 'site-scanner-monthly.csv');
  flash('Downloaded');
}
function exportGeoJson() {
  const props = { name: 'Site Scanner AOI', area_ha: +S.areaHa.toFixed(2), demo: true, exported: new Date().toISOString() };
  for (const c of cols()) {
    props[c.id] = Object.fromEntries(c.annual.map(r => [r.year, r.value]));
    props[c.id + '__meta'] = { name: c.f.name, unit: c.f.unit, source: B_BY_ID[c.f.base].name, licence: B_BY_ID[c.f.base].licence };
  }
  const fc = { type: 'FeatureCollection', features: [{ type: 'Feature', properties: props,
    geometry: { type: 'Polygon', coordinates: [S.aoi] } }] };
  dl(new Blob([JSON.stringify(fc, null, 2)], { type: 'application/geo+json' }), 'site-scanner-aoi.geojson');
  flash('Downloaded');
}
function printReport() {
  const cs = cols();
  const w = window.open('', '_blank');
  if (!w) { flash('Allow pop-ups to print', true); return; }
  const rows = cs[0].annual.map(r0 => `<tr><th>${r0.year}</th>` +
    cs.map(c => `<td>${fmt(c.annual.find(a => a.year === r0.year).value, c.f)}</td>`).join('') + '</tr>').join('');
  w.document.write(`<!doctype html><meta charset="utf-8"><title>Site Scanner report</title>
<style>body{font:12px/1.5 -apple-system,system-ui,sans-serif;margin:32px;color:#111}
h1{font-size:18px;margin:0 0 4px}.sub{color:#666;margin-bottom:20px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{border-bottom:1px solid #ddd;padding:5px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}thead th{border-bottom:2px solid #333;font-size:11px}
.src{margin-top:24px;font-size:10px;color:#666}@media print{body{margin:12mm}}</style>
<h1>Site Scanner — site report</h1>
<div class="sub">${S.areaHa.toFixed(1)} ha · centred ${S.centroid[1].toFixed(4)}, ${S.centroid[0].toFixed(4)}
 · ${new Date().toLocaleDateString('en-GB')} · <b>demo data, not observed</b></div>
<table><thead><tr><th>Year</th>${cs.map(c => `<th>${esc(c.f.name)}<br><span style="font-weight:400;color:#888">${esc(c.f.unit)}</span></th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>
<div class="src"><b>Sources.</b> ${[...new Set(cs.map(c => `${B_BY_ID[c.f.base].name} (${B_BY_ID[c.f.base].licence})`))].join(' · ')}</div>`);
  w.document.close(); w.focus();
  setTimeout(() => w.print(), 350);
}

/* ---------- saved sites ---------- */
const SAVED_KEY = 'site-scanner.demo.saved';
function loadSavedSites() { try { S.saved = JSON.parse(localStorage.getItem(SAVED_KEY) || '[]'); } catch { S.saved = []; } }
function persistSaved() { try { localStorage.setItem(SAVED_KEY, JSON.stringify(S.saved)); } catch {} }

function sitesMenu() {
  return S.saved.map(s => {
    const row = el('div', 'row');
    const load = el('button', null, `${esc(s.name)}<span>${fmtArea(s.area)}</span>`);
    load.onclick = () => { closeMenus(); setAoi(s.ring); };
    const del = el('button', 'del', '×');
    del.title = 'Delete';
    del.onclick = e => { e.stopPropagation(); S.saved = S.saved.filter(x => x.id !== s.id); persistSaved(); openMenu($('#sitesBtn'), []); openMenu($('#sitesBtn'), sitesMenu()); };
    row.append(load, del);
    return { row };
  });
}

/* ---------- events ---------- */
$('#t-rect').onclick = () => setTool('rect');
$('#t-circle').onclick = () => setTool('circle');
$('#t-free').onclick = () => setTool('free');
$('#clearBtn').onclick = () => setAoi(null);
$('#fitBtn').onclick = () => { viewInit = false; fitView(VIEW.w, VIEW.h); drawMap(); };
$('#undoBtn').onclick = () => {
  if (!S.past.length) return;
  S.future.unshift(S.aoi);
  const prev = S.past.pop();
  prev ? setAoi(prev, { skipHistory: true }) : setAoi(null, { skipHistory: true });
};
$('#redoBtn').onclick = () => {
  if (!S.future.length) return;
  S.past.push(S.aoi);
  const next = S.future.shift();
  next ? setAoi(next, { skipHistory: true }) : setAoi(null, { skipHistory: true });
};
$('#browserBtn').onclick = () => toggleBrowser(!browserNode);
$('#tplBtn').onclick = openTemplates;
$('#saveBtn').onclick = () => {
  const name = prompt('Name this site', 'Untitled site');
  if (name === null) return;
  S.saved.unshift({ id: String(Date.now()), name: name.trim() || 'Untitled site', ring: S.aoi, area: S.areaHa });
  S.saved = S.saved.slice(0, 50);
  persistSaved(); flash('Saved');
};
$('#sitesBtn').onclick = () => openMenu($('#sitesBtn'), sitesMenu());
$('#shareBtn').onclick = () => {
  syncUrl();
  navigator.clipboard.writeText(location.href)
    .then(() => flash('Link copied — it restores this exact view'))
    .catch(() => flash('Copy the address bar to share this view'));
};
$('#exportBtn').onclick = () => openMenu($('#exportBtn'), [
  { label: 'CSV — one row per year', run: exportAnnual },
  { label: 'CSV — every month, with confidence', run: exportMonthly },
  { label: 'GeoJSON — shape plus data', run: exportGeoJson },
  { label: 'Printable report / PDF', run: printReport },
]);
document.addEventListener('click', e => {
  if (S.menu && !e.target.closest('.menu') && !e.target.closest('.btn')) closeMenus();
});
for (const t of document.querySelectorAll('.tab'))
  t.onclick = () => { S.tab = t.dataset.tab; render(); };

const range = $('#range');
range.addEventListener('input', e => { S.t = +e.target.value; render(); drawMap(); drawSpark(); syncUrl(); });
range.addEventListener('pointerdown', e => {
  // Shift-click pins a second position rather than moving the head, which
  // keeps comparison one gesture away instead of a mode.
  if (!e.shiftKey) return;
  e.preventDefault();
  const r = range.getBoundingClientRect();
  S.compare = Math.max(0, Math.min(STEPS.length - 1, Math.round((e.clientX - r.left) / r.width * (STEPS.length - 1))));
  S.tab = 'charts';
  render(); drawSpark(); syncUrl();
});

let raf = 0, acc = 0, last = 0;
function tick(now) {
  acc += now - last; last = now;
  if (acc >= 70) { const step = Math.floor(acc / 70); acc -= step * 70; S.t = (S.t + step) % STEPS.length; render(); drawMap(); drawSpark(); }
  raf = requestAnimationFrame(tick);
}
$('#playBtn').onclick = () => {
  S.playing = !S.playing;
  $('#playBtn').innerHTML = S.playing
    ? '<svg viewBox="0 0 16 16" width="15" height="15" fill="currentColor"><rect x="3.5" y="2.5" width="3.2" height="11" rx=".8"/><rect x="9.3" y="2.5" width="3.2" height="11" rx=".8"/></svg>'
    : '<svg viewBox="0 0 16 16" width="15" height="15" fill="currentColor"><path d="M4.5 2.5l9 5.5-9 5.5z"/></svg>';
  $('#playBtn').setAttribute('aria-label', S.playing ? 'Pause playback' : 'Play through time');
  if (S.playing) { last = performance.now(); acc = 0; raf = requestAnimationFrame(tick); }
  else { cancelAnimationFrame(raf); syncUrl(); }
};

window.addEventListener('keydown', e => {
  if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;
  const move = d => { S.t = Math.max(0, Math.min(STEPS.length - 1, S.t + d)); render(); drawMap(); drawSpark(); syncUrl(); e.preventDefault(); };
  if (e.key === 'ArrowLeft') move(-1);
  else if (e.key === 'ArrowRight') move(1);
  else if (e.key === 'PageDown') move(-12);
  else if (e.key === 'PageUp') move(12);
  else if (e.key === 'Home') { S.t = 0; render(); drawMap(); drawSpark(); e.preventDefault(); }
  else if (e.key === 'End') { S.t = STEPS.length - 1; render(); drawMap(); drawSpark(); e.preventDefault(); }
  else if (e.key === ' ') { $('#playBtn').click(); e.preventDefault(); }
  else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
    e.preventDefault();
    (e.shiftKey ? $('#redoBtn') : $('#undoBtn')).click();
  } else if (e.key === 'Escape') { closeMenus(); if (browserNode) toggleBrowser(false); }
});

/* Drag a GeoJSON boundary anywhere onto the window. Most serious users already
   have their shape in a file; making them re-trace it is exactly the friction
   this product exists to remove. */
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', async e => {
  e.preventDefault();
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  try {
    const json = JSON.parse(await file.text());
    const ring = findRing(json);
    if (!ring) throw new Error('No polygon in that file.');
    setAoi(ring);
    flash(`Loaded ${file.name}`);
  } catch (err) {
    flash(err.message || 'Could not read that file.', true);
  }
});
function findRing(n) {
  if (!n || typeof n !== 'object') return null;
  if (n.type === 'Polygon') return n.coordinates[0];
  if (n.type === 'MultiPolygon') return n.coordinates.reduce((a, b) => (b[0]?.length ?? 0) > (a[0]?.length ?? 0) ? b : a)[0];
  if (n.type === 'Feature') return findRing(n.geometry);
  if (n.type === 'FeatureCollection') { for (const f of n.features || []) { const r = findRing(f); if (r) return r; } }
  return n.geometry ? findRing(n.geometry) : null;
}

/* Repaint on theme change — the canvases read CSS custom properties, so a
   theme flip must be redrawn rather than restyled. */
/* One identity, no dark variant — nothing to repaint when the OS theme flips. */
new MutationObserver(() => { drawMap(); drawSpark(); render(); })
  .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

window.addEventListener('resize', sizeMap);

/* ---------- boot ---------- */
(function init() {
  const yrs = $('#years');
  STEPS.forEach((s, i) => {
    const y = +s.slice(0, 4);
    if (s.endsWith('-01') && y % 3 === 0) {
      const n = el('span', null, String(y));
      n.style.left = (i / (STEPS.length - 1) * 100) + '%';
      yrs.appendChild(n);
    }
  });
  loadSavedSites();
  sizeMap();
  if (!hydrate()) {
    // Open on a worked example rather than a blank map — a first-time visitor
    // should see the product working before being asked to do anything.
    // Roughly 900 ha of farmland north-east of Coventry — a real working
    // scale, not a county.
    const ring = circleRing([-1.470, 52.620], [-1.442, 52.620]);
    // frame:false — open on the whole country with the example marked on it,
    // rather than dropping the user into a field with no context.
    setAoi(ring, { skipHistory: true, frame: false });
    S.past = [];
  }
  render(); drawMap(); drawSpark();
})();
