/* =====================================================================
   Site Scanner — rendering: table, charts, sources, timeline
   ===================================================================== */

function cols() { return S.selected.map(id => S.series[id]).filter(Boolean); }

/* ---------- table ---------- */
function renderTable(root) {
  const cs = cols();
  if (!cs.length) return;
  const years = cs[0].annual.map(r => r.year);
  const sorted = [...years];
  if (S.sort.col === 'year') sorted.sort((a, b) => S.sort.asc ? a - b : b - a);
  else {
    const s = cs.find(c => c.id === S.sort.col);
    if (s) {
      const by = new Map(s.annual.map(r => [r.year, r.value]));
      sorted.sort((a, b) => {
        const va = by.get(a), vb = by.get(b);
        if (va === null) return 1; if (vb === null) return -1;
        if (typeof va === 'string') return S.sort.asc ? String(va).localeCompare(vb) : String(vb).localeCompare(va);
        return S.sort.asc ? va - vb : vb - va;
      });
    }
  }
  const nowYear = +STEPS[S.t].slice(0, 4);

  const bar = el('div', 'tbar');
  bar.innerHTML = `<span>one row per year · ${years.length} years · ${cs.length} factor${cs.length > 1 ? 's' : ''}</span>`;
  const acts = el('div');
  const copyBtn = el('button', 'btn', 'Copy');
  copyBtn.title = 'Copy as TSV — pastes straight into Excel';
  copyBtn.onclick = () => {
    const lines = [['Year', ...cs.map(c => `${c.f.name} (${c.f.unit})`)].join('\t')];
    for (const y of sorted) lines.push([y, ...cs.map(c => {
      const r = c.annual.find(a => a.year === y); return r && r.value !== null ? r.value : '';
    })].join('\t'));
    navigator.clipboard.writeText(lines.join('\n')).then(() => flash('Copied — paste into Excel'));
  };
  acts.appendChild(copyBtn);
  bar.appendChild(acts);
  root.appendChild(bar);

  const scroll = el('div', 'tscroll');
  const t = el('table', 'grid');
  const thead = el('thead');
  const hr = el('tr');
  const th0 = el('th', 'yr', `Year ${S.sort.col === 'year' ? (S.sort.asc ? '▲' : '▼') : ''}`);
  th0.onclick = () => { S.sort = { col: 'year', asc: S.sort.col === 'year' ? !S.sort.asc : true }; render(); };
  hr.appendChild(th0);
  for (const c of cs) {
    const th = el('th', null, `${esc(c.f.name)}<u>${esc(c.f.unit)}</u>${S.sort.col === c.id ? (S.sort.asc ? ' ▲' : ' ▼') : ''}`);
    th.title = `${c.f.note}\n\nSource: ${B_BY_ID[c.f.base].name}`;
    th.onclick = () => { S.sort = { col: c.id, asc: S.sort.col === c.id ? !S.sort.asc : false }; render(); };
    hr.appendChild(th);
  }
  thead.appendChild(hr); t.appendChild(thead);

  const tb = el('tbody');
  for (const y of sorted) {
    const open = S.expanded.has(y);
    const tr = el('tr', `year${y === nowYear ? ' now' : ''}${open ? ' open' : ''}`);
    tr.onclick = () => { open ? S.expanded.delete(y) : S.expanded.add(y); render(); };
    tr.appendChild(el('td', 'yr', `<span class="caret">${open ? '▾' : '▸'}</span>${y}`));
    for (const c of cs) {
      const r = c.annual.find(a => a.year === y);
      const td = el('td', band(r.conf));
      td.innerHTML = fmt(r.value, c.f) +
        (r.obs < r.total && r.value !== null ? '<span class="part">·</span>' : '');
      td.title = r.value === null ? 'No usable observation this year'
        : `${r.obs} of ${r.total} months observed` +
          (r.min !== null ? ` · range ${fmt(r.min, c.f)}–${fmt(r.max, c.f)}` : '');
      tr.appendChild(td);
    }
    tb.appendChild(tr);

    if (open) {
      cs[0].points.forEach((p, idx) => {
        if (+p.t.slice(0, 4) !== y) return;
        const mr = el('tr', `mo${idx === S.t ? ' now' : ''}`);
        mr.title = 'Jump the timeline to this month';
        mr.onclick = e => { e.stopPropagation(); S.t = idx; render(); drawMap(); drawSpark(); syncUrl(); };
        mr.appendChild(el('td', 'yr molab', MONTHS[+p.t.slice(5) - 1]));
        for (const c of cs) {
          const q = c.points[idx];
          const td = el('td', band(q.valid));
          td.innerHTML = q.value === null ? '<span class="gapv" title="No usable observation">—</span>' : fmt(q.value, c.f);
          mr.appendChild(td);
        }
        tb.appendChild(mr);
      });
    }
  }
  t.appendChild(tb); scroll.appendChild(t); root.appendChild(scroll);
}

/* ---------- charts ---------- */
function inferCharts(cs) {
  const cont = cs.filter(c => c.f.kind === 'continuous');
  const cat = cs.filter(c => c.f.kind === 'categorical');
  const specs = [];

  // Never mix units on one axis: °C and mm sharing a y-axis is a lie told
  // with a straight face.
  const byUnit = new Map();
  for (const c of cont) { const u = c.f.unit || 'value'; if (!byUnit.has(u)) byUnit.set(u, []); byUnit.get(u).push(c); }
  for (const [unit, group] of byUnit)
    specs.push({ type: 'line', unit, group,
      title: group.length === 1 ? `${group[0].f.name} over time` : `${group.map(g => g.f.name).join(', ')} over time`,
      why: `${group.length} factor${group.length > 1 ? 's' : ''} measured in ${unit}` });

  const lc = cont.filter(c => c.f.unit === '%' && c.id.startsWith('lc_'));
  if (lc.length >= 2)
    specs.push({ type: 'stack', group: lc, title: 'Land cover composition',
                 why: 'Shares of one whole read better stacked than overlaid' });

  for (const c of cat)
    specs.push({ type: 'bar', group: [c], title: `${c.f.name} — years per class`,
                 why: 'Categorical data cannot be averaged, so this counts instead' });

  if (cont.length >= 2) {
    let best = null;
    for (let i = 0; i < cont.length; i++) for (let j = i + 1; j < cont.length; j++) {
      const r = corr(cont[i], cont[j]);
      if (Math.abs(r) > 0.6 && (!best || Math.abs(r) > Math.abs(best.r))) best = { a: cont[i], b: cont[j], r };
    }
    if (best) specs.push({ type: 'scatter', group: [best.a, best.b], r: best.r,
      title: `${best.a.f.name} vs ${best.b.f.name}`,
      why: `Correlated at r = ${best.r.toFixed(2)} across the years shown` });
  }
  return specs.slice(0, 4);   // four is the ceiling; more is noise nobody reads
}

function corr(a, b) {
  const ma = new Map(a.annual.map(r => [r.year, r.value]));
  const xs = [], ys = [];
  for (const r of b.annual) {
    const v = ma.get(r.year);
    if (typeof v === 'number' && typeof r.value === 'number') { xs.push(v); ys.push(r.value); }
  }
  if (xs.length < 5) return 0;
  const mx = xs.reduce((s, v) => s + v, 0) / xs.length, my = ys.reduce((s, v) => s + v, 0) / ys.length;
  let n = 0, da = 0, db = 0;
  for (let i = 0; i < xs.length; i++) { const x = xs[i] - mx, y = ys[i] - my; n += x * y; da += x * x; db += y * y; }
  return da && db ? n / Math.sqrt(da * db) : 0;
}

const CW = 380, CH = 168, ML = 46, MR = 8, MT = 8, MB = 22;
function svgEl(inner) {
  return `<svg viewBox="0 0 ${CW} ${CH}" preserveAspectRatio="xMidYMid meet" role="img">${inner}</svg>`;
}
function axes(yLo, yHi, xLabels) {
  const gridCol = isLight() ? 'rgba(20,26,30,.10)' : 'rgba(255,255,255,.07)';
  const txt = cssVar('--ink-3');
  let s = '';
  for (let i = 0; i <= 4; i++) {
    const y = MT + (CH - MT - MB) * (i / 4);
    const v = yHi - (yHi - yLo) * (i / 4);
    s += `<line x1="${ML}" y1="${y}" x2="${CW - MR}" y2="${y}" stroke="${gridCol}" stroke-width="1"/>`;
    s += `<text x="${ML - 6}" y="${y + 3}" text-anchor="end" font-size="9" font-family="ui-monospace,monospace" fill="${txt}">${compact(v)}</text>`;
  }
  for (const [frac, label] of xLabels)
    s += `<text x="${ML + (CW - ML - MR) * frac}" y="${CH - 6}" text-anchor="middle" font-size="9" font-family="ui-monospace,monospace" fill="${txt}">${label}</text>`;
  return s;
}
const xAt = f => ML + (CW - ML - MR) * f;
const yAt = (v, lo, hi) => MT + (CH - MT - MB) * (1 - (v - lo) / (hi - lo || 1));

function yearTicks() {
  const out = [];
  STEPS.forEach((s, i) => {
    const y = +s.slice(0, 4);
    if (s.endsWith('-01') && y % 3 === 0) out.push([i / (STEPS.length - 1), String(y)]);
  });
  return out;
}

function chartLine(spec) {
  const all = spec.group.flatMap(g => g.points.map(p => p.value).filter(v => v !== null));
  if (all.length < 2) return '';
  let lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;

  let s = axes(lo, hi, yearTicks());
  spec.group.forEach((g, gi) => {
    let d = '', pen = false;
    g.points.forEach((p, i) => {
      if (p.value === null) { pen = false; return; }   // gaps stay gaps
      const x = xAt(i / (STEPS.length - 1)), y = yAt(p.value, lo, hi);
      d += (pen ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
      pen = true;
    });
    s += `<path d="${d}" fill="none" stroke="${sColor(gi)}" stroke-width="1.5" stroke-linejoin="round"/>`;
  });
  const mx = xAt(S.t / (STEPS.length - 1));
  s += `<line x1="${mx}" y1="${MT}" x2="${mx}" y2="${CH - MB}" stroke="${cssVar('--accent')}" stroke-width="1.5" opacity=".85"/>`;
  if (S.compare !== null) {
    const cx = xAt(S.compare / (STEPS.length - 1));
    s += `<line x1="${cx}" y1="${MT}" x2="${cx}" y2="${CH - MB}" stroke="${cssVar('--good')}" stroke-width="1.5" stroke-dasharray="3 2" opacity=".9"/>`;
  }
  return svgEl(s);
}

function chartStack(spec) {
  const years = spec.group[0].annual.map(r => r.year);
  const totals = years.map((_, i) => spec.group.reduce((a, g) => a + (g.annual[i].value || 0), 0));
  const hi = Math.max(...totals) * 1.05 || 1;
  let s = axes(0, hi, years.map((y, i) => [i / (years.length - 1), i % 3 === 0 ? String(y) : '']).filter(t => t[1]));
  const acc = years.map(() => 0);
  spec.group.forEach((g, gi) => {
    let up = '', down = '';
    years.forEach((_, i) => {
      const x = xAt(i / (years.length - 1));
      const base = acc[i], top = base + (g.annual[i].value || 0);
      up += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + yAt(top, 0, hi).toFixed(1) + ' ';
      acc[i] = top;
    });
    for (let i = years.length - 1; i >= 0; i--) {
      const x = xAt(i / (years.length - 1));
      down += 'L' + x.toFixed(1) + ' ' + yAt(acc[i] - (spec.group[gi].annual[i].value || 0), 0, hi).toFixed(1) + ' ';
    }
    s += `<path d="${up}${down}Z" fill="${sColor(gi)}" opacity=".8"/>`;
  });
  return svgEl(s);
}

function chartBar(spec) {
  const g = spec.group[0];
  const counts = {};
  for (const r of g.annual) if (typeof r.value === 'string') counts[r.value] = (counts[r.value] || 0) + 1;
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!rows.length) return '';
  const hi = Math.max(...rows.map(r => r[1]));
  const bh = Math.min(20, (CH - MT - MB) / rows.length - 4);
  const L = 96;
  let s = '';
  rows.forEach(([name, n], i) => {
    const y = MT + i * ((CH - MT - MB) / rows.length);
    const w = (CW - L - MR) * (n / hi);
    s += `<rect x="${L}" y="${y}" width="${w.toFixed(1)}" height="${bh}" rx="2" fill="${sColor(1)}" opacity=".85"/>`;
    s += `<text x="${L - 6}" y="${y + bh / 2 + 3}" text-anchor="end" font-size="9.5" fill="${cssVar('--ink-2')}">${esc(name)}</text>`;
    s += `<text x="${L + w + 5}" y="${y + bh / 2 + 3}" font-size="9" font-family="ui-monospace,monospace" fill="${cssVar('--ink-3')}">${n}</text>`;
  });
  return svgEl(s);
}

function chartScatter(spec) {
  const [a, b] = spec.group;
  const mb = new Map(b.annual.map(r => [r.year, r.value]));
  const pts = a.annual.filter(r => typeof r.value === 'number' && typeof mb.get(r.year) === 'number')
    .map(r => [r.value, mb.get(r.year)]);
  if (pts.length < 3) return '';
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const xlo = Math.min(...xs), xhi = Math.max(...xs), ylo = Math.min(...ys), yhi = Math.max(...ys);
  let s = axes(ylo, yhi, [[0, compact(xlo)], [1, compact(xhi)]]);
  for (const [x, y] of pts)
    s += `<circle cx="${xAt((x - xlo) / (xhi - xlo || 1)).toFixed(1)}" cy="${yAt(y, ylo, yhi).toFixed(1)}" r="3.2" fill="${sColor(0)}" opacity=".85"/>`;
  // Least-squares fit, drawn only because the correlation cleared the bar.
  const n = pts.length, sx = xs.reduce((p, c) => p + c, 0), sy = ys.reduce((p, c) => p + c, 0);
  const sxy = pts.reduce((p, [x, y]) => p + x * y, 0), sxx = xs.reduce((p, x) => p + x * x, 0);
  const m = (n * sxy - sx * sy) / (n * sxx - sx * sx || 1), c0 = (sy - m * sx) / n;
  s += `<line x1="${xAt(0)}" y1="${yAt(m * xlo + c0, ylo, yhi).toFixed(1)}" x2="${xAt(1)}" y2="${yAt(m * xhi + c0, ylo, yhi).toFixed(1)}" stroke="${cssVar('--good')}" stroke-width="1.3" opacity=".65"/>`;
  return svgEl(s);
}

function renderCharts(root) {
  const cs = cols();
  const stack = el('div', 'stack');
  if (S.compare !== null) stack.appendChild(compareCard(cs));

  for (const spec of inferCharts(cs)) {
    const card = el('div', 'card');
    card.innerHTML = `<h3>${esc(spec.title)}</h3><div class="why">${esc(spec.why)}</div>`;
    const body =
      spec.type === 'line' ? chartLine(spec) :
      spec.type === 'stack' ? chartStack(spec) :
      spec.type === 'bar' ? chartBar(spec) : chartScatter(spec);
    card.insertAdjacentHTML('beforeend', body);
    if (spec.group.length > 1 && spec.type !== 'scatter') {
      card.insertAdjacentHTML('beforeend',
        `<div class="legend">${spec.group.map((g, i) =>
          `<span><i style="background:${sColor(i)}"></i>${esc(g.f.name)}</span>`).join('')}</div>`);
    }
    if (spec.type === 'line') {
      const svg = card.querySelector('svg');
      svg.style.cursor = 'crosshair';
      svg.onclick = ev => {
        const r = svg.getBoundingClientRect();
        const frac = ((ev.clientX - r.left) / r.width * CW - ML) / (CW - ML - MR);
        S.t = Math.max(0, Math.min(STEPS.length - 1, Math.round(frac * (STEPS.length - 1))));
        render(); drawMap(); drawSpark(); syncUrl();
      };
    }
    stack.appendChild(card);
  }
  root.appendChild(stack);
}

function compareCard(cs) {
  const [lo, hi] = S.t <= S.compare ? [S.t, S.compare] : [S.compare, S.t];
  const card = el('div', 'card cmp');
  const months = (+STEPS[hi].slice(0, 4) - +STEPS[lo].slice(0, 4)) * 12 +
                 (+STEPS[hi].slice(5) - +STEPS[lo].slice(5));
  card.innerHTML = `<div class="cmp-head">
      <div><h3>Change · ${labelStep(STEPS[lo])} → ${labelStep(STEPS[hi])}</h3>
      <div class="why">${months} months apart</div></div></div>`;
  const clear = el('button', 'btn', 'Clear');
  clear.onclick = () => { S.compare = null; render(); drawSpark(); syncUrl(); };
  card.querySelector('.cmp-head').appendChild(clear);

  const t = el('table', 'cmp');
  t.innerHTML = `<thead><tr><th>Factor</th><th>${labelStep(STEPS[lo])}</th><th>${labelStep(STEPS[hi])}</th><th>Change</th></tr></thead>`;
  const tb = el('tbody');
  for (const c of cs) {
    const a = c.points[lo].value, b = c.points[hi].value;
    const tr = el('tr');
    let cell;
    if (a === null || b === null) cell = `<td class="gapv" title="No usable observation at one end">—</td>`;
    else if (typeof a === 'string') {
      cell = a !== b ? `<td class="chg">changed</td>` : `<td class="same">no change</td>`;
    } else {
      const d = b - a, pct = a !== 0 ? d / Math.abs(a) * 100 : null;
      const dir = d > 0 ? 'up' : d < 0 ? 'down' : 'flat';
      cell = `<td class="${dir}">${d > 0 ? '+' : ''}${fmt(d, c.f)}` +
        (pct !== null && Math.abs(pct) < 1000 ? ` <span class="pct">${d > 0 ? '+' : ''}${pct.toFixed(0)}%</span>` : '') + `</td>`;
    }
    tr.innerHTML = `<td>${esc(c.f.name)}</td><td>${fmt(a, c.f)}</td><td>${fmt(b, c.f)}</td>${cell}`;
    tb.appendChild(tr);
  }
  t.appendChild(tb); card.appendChild(t);
  card.insertAdjacentHTML('beforeend',
    `<div class="note">Comparing two single months carries their weather with it. For a trend, read the chart rather than the endpoints.</div>`);
  return card;
}

/* ---------- sources ---------- */
function renderSources(root) {
  const stack = el('div', 'stack');
  const byBase = new Map();
  for (const c of cols()) {
    if (!byBase.has(c.f.base)) byBase.set(c.f.base, []);
    byBase.get(c.f.base).push(c);
  }
  for (const [baseId, list] of byBase) {
    const b = B_BY_ID[baseId];
    const card = el('div', 'src');
    card.innerHTML = `<h3>${esc(b.name)}</h3>
      <dl>
        <dt>Source</dt><dd>${esc(b.source)}</dd>
        <dt>Licence</dt><dd>${esc(b.licence)}</dd>
        <dt>Resolution</dt><dd>${b.res ? b.res + ' m' : 'Vector / tabular'}</dd>
        <dt>Native cadence</dt><dd>${esc(b.native)}</dd>
        <dt>Stored cadence</dt><dd>${esc(b.cadence)}</dd>
        <dt>Held by us</dt><dd>${b.stored ? 'Yes — served from our storage' : 'No — queried live'}</dd>
      </dl>
      <div class="chips">${list.map(c =>
        `<span class="chip" title="${esc(c.f.note)}">${esc(c.f.name)}${c.f.derived ? ' <em>ƒ</em>' : ''}</span>`).join('')}</div>
      <a href="${esc(b.url)}" target="_blank" rel="noreferrer">${esc(b.url.replace(/^https?:\/\//, '').replace(/\/$/, ''))} ↗</a>`;
    stack.appendChild(card);
  }
  root.appendChild(stack);
}

/* ---------- timeline sparkline ---------- */
const sparkCv = $('#spark'), sparkCtx = sparkCv.getContext('2d');
function drawSpark() {
  const r = sparkCv.getBoundingClientRect();
  const dpr = devicePixelRatio || 1;
  sparkCv.width = r.width * dpr; sparkCv.height = r.height * dpr;
  sparkCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = r.width, h = r.height;
  sparkCtx.clearRect(0, 0, w, h);
  if (!w) return;

  const stripH = 5, chartH = h - stripH - 3;
  sparkCtx.strokeStyle = isLight() ? 'rgba(20,26,30,.07)' : 'rgba(255,255,255,.05)';
  sparkCtx.lineWidth = 1;
  STEPS.forEach((s, i) => {
    if (!s.endsWith('-01')) return;
    const x = i / (STEPS.length - 1) * w;
    sparkCtx.beginPath(); sparkCtx.moveTo(x, 0); sparkCtx.lineTo(x, chartH); sparkCtx.stroke();
  });

  const ser = S.series[S.selected[0]];
  if (!ser || ser.f.kind === 'categorical') return;
  const vals = ser.points.map(p => p.value);
  const present = vals.filter(v => v !== null);
  if (present.length < 2) return;
  const lo = Math.min(...present), hi = Math.max(...present), span = hi - lo || 1;
  const X = i => i / (STEPS.length - 1) * w;
  const Y = v => chartH - ((v - lo) / span) * (chartH - 6) - 3;

  // Fill under the line, broken at gaps.
  sparkCtx.fillStyle = isLight() ? 'rgba(162,112,28,.14)' : 'rgba(221,174,92,.13)';
  let run = -1;
  for (let i = 0; i <= vals.length; i++) {
    if (vals[i] !== null && vals[i] !== undefined) { if (run < 0) run = i; continue; }
    if (run >= 0 && i - run > 1) {
      sparkCtx.beginPath(); sparkCtx.moveTo(X(run), chartH);
      for (let k = run; k < i; k++) sparkCtx.lineTo(X(k), Y(vals[k]));
      sparkCtx.lineTo(X(i - 1), chartH); sparkCtx.closePath(); sparkCtx.fill();
    }
    run = -1;
  }

  sparkCtx.strokeStyle = sColor(0); sparkCtx.lineWidth = 1.5; sparkCtx.lineJoin = 'round';
  let pen = false; sparkCtx.beginPath();
  vals.forEach((v, i) => {
    if (v === null) { pen = false; return; }
    pen ? sparkCtx.lineTo(X(i), Y(v)) : sparkCtx.moveTo(X(i), Y(v));
    pen = true;
  });
  sparkCtx.stroke();

  if (S.compare !== null) {
    sparkCtx.strokeStyle = cssVar('--good'); sparkCtx.lineWidth = 1.5;
    sparkCtx.setLineDash([3, 2]);
    sparkCtx.beginPath(); sparkCtx.moveTo(X(S.compare), 0); sparkCtx.lineTo(X(S.compare), chartH); sparkCtx.stroke();
    sparkCtx.setLineDash([]);
  }

  // Availability strip: how much of the area produced a usable observation.
  const bw = Math.max(1, w / STEPS.length);
  ser.points.forEach((p, i) => {
    sparkCtx.fillStyle = p.value === null
      ? 'rgba(196,123,114,.6)'
      : `rgba(127,179,163,${0.18 + 0.62 * p.valid})`;
    sparkCtx.fillRect(X(i) - bw / 2, chartH + 3, bw, stripH);
  });
}
