import type { Brief } from '../types'

/**
 * Rendering the Site Investigation Brief as a document.
 *
 * The Brief leaves the product. That changes what the rendering has to do:
 * there is no tab to click, no tooltip to hover and nobody present to explain
 * what a word means, so every qualification has to be *in the text*, next to
 * the thing it qualifies.
 *
 * The server decided all of it — states, claims, causes, order. This module
 * escapes and lays out. It computes no state and composes no claim, which is
 * `EM11` applied to a document.
 */

/** Text into a document that will be printed, mailed and pasted. */
export function escapeHtml(s: string): string {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-GB',
    { day: 'numeric', month: 'long', year: 'numeric' })
}

/** "155.16 ha · 51.2390, -0.5720". Never a county — a drawn shape has none. */
export function siteLine(b: Brief): string {
  const parts: string[] = []
  if (b.site.area_ha != null) parts.push(`${b.site.area_ha.toLocaleString()} ha`)
  if (b.site.centroid) {
    parts.push(`${b.site.centroid.lat.toFixed(4)}, ${b.site.centroid.lng.toFixed(4)}`)
  }
  return parts.join(' · ')
}

/**
 * "1 of 24 factors assessed · 23 not assessed".
 *
 * Both halves, always. The partition that actually holds is
 * `assessed + not_assessed = relevant`; the four finding states are not a
 * partition, so the document reports the one a reader can check.
 */
export function coverageLine(b: Brief): string {
  const c = b.coverage
  return `${c.assessed} of ${c.relevant} factors assessed · ${c.not_assessed} not assessed`
}

/** Findings are numbered so a reader can refer to one by number in an email
 *  or a phone call. That is the whole reason, and it is enough of one. */
export function findingNumber(i: number): string {
  return String(i + 1).padStart(2, '0')
}

function section(title: string, body: string): string {
  return `<section class="s"><h2>${escapeHtml(title)}</h2>${body}</section>`
}

function list(items: string[]): string {
  return items.length
    ? `<ul>${items.map((i) => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`
    : ''
}

/**
 * The whole document.
 *
 * Section order comes from the server (`brief.sections`) rather than from the
 * order of calls here, because the order is an editorial decision the backend
 * owns and states its reasoning for — coverage before findings, always.
 */
export function briefHtml(b: Brief): string {
  const parts: string[] = []

  parts.push(`
    <header class="head">
      <p class="kicker">Site investigation brief</p>
      <h1>${escapeHtml(b.site.name)}</h1>
      <p class="sub">${escapeHtml(siteLine(b))}</p>
      <p class="sub">Assessed ${escapeHtml(formatDate(b.site.assessed_at))}</p>
    </header>`)

  for (const name of b.sections) {
    if (name === 'site') continue

    if (name === 'coverage') {
      parts.push(section('Evidence coverage', `
        <p class="lead">${escapeHtml(coverageLine(b))}</p>
        <table class="kv"><tbody>
          <tr><th>Flagged</th><td>${b.coverage.flagged}</td></tr>
          <tr><th>Checked · clear</th><td>${b.coverage.clear}</td></tr>
          <tr><th>Informational</th><td>${b.coverage.informational}</td></tr>
          <tr><th>Not assessed</th><td>${b.coverage.not_assessed}</td></tr>
        </tbody></table>
        <p class="note">${escapeHtml(b.coverage.note)}</p>`))
    }

    if (name === 'findings') {
      const body = b.findings.length
        ? b.findings.map((f, i) => `
            <article class="finding">
              <p class="fnum">${findingNumber(i)}</p>
              <h3>${escapeHtml(f.name)}</h3>
              ${/* The finding text is NOT printed here. `claims.established` is
                    composed from exactly these strings, so printing both put
                    every finding on the page twice — and the second copy, sat
                    under "what this establishes", was the one that mattered.
                    The threshold line carries what the narrative would have. */''}
              ${f.findings.map((x) => x.threshold
                  ? `<p class="fthresh">Threshold: ${escapeHtml(x.threshold)}${
                       x.method ? ` · method ${escapeHtml(x.method)}` : ''}</p>`
                  : '').join('')}
              <div class="claims">
                <div><h4>What this establishes</h4>
                  ${f.established.map((c) => `<p>${escapeHtml(c)}</p>`).join('')}</div>
                <div><h4>What this does not establish</h4>
                  ${f.not_established.map((c) => `<p>${escapeHtml(c)}</p>`).join('')}</div>
              </div>
              ${f.investigations.length ? `<p class="prompt"><strong>Investigation prompted:</strong>
                 ${escapeHtml(f.investigations.join(', '))}</p>` : ''}
            </article>`).join('')
        /* Not "no issues found". With most of the catalogue generated, an
           empty findings list far more often means nothing could be checked
           than that nothing is there — and this is the section a reader skims
           first. */
        : `<p class="lead">No finding crossed a reporting threshold in the
             evidence that could be read. See evidence gaps below.</p>`
      parts.push(section('Key findings', body))
    }

    if (name === 'historical' && b.historical.length) {
      parts.push(section('Historical change', `
        <table class="rows"><tbody>
          ${b.historical.map((h) => `
            <tr>
              <th>${escapeHtml(h.name)}</th>
              <td>${h.change_pct == null ? '—'
                    : `${h.change_pct > 0 ? '+' : ''}${h.change_pct.toFixed(1)}%`}</td>
              <td>${escapeHtml(h.state.replace(/_/g, ' '))}</td>
              <td class="dim">${h.years_usable ?? '—'} of ${h.years_total ?? '—'} years
                  · ${escapeHtml(h.method)}</td>
            </tr>`).join('')}
        </tbody></table>`))
    }

    if (name === 'gaps') {
      parts.push(section('Evidence gaps', b.gaps.length
        ? b.gaps.map((g) => `
            <div class="gap">
              <p><strong>${g.count}</strong> ${escapeHtml(g.label)}</p>
              <p class="dim">${escapeHtml(g.factors.join(', '))}</p>
            </div>`).join('')
        : '<p class="lead">Every relevant factor was assessed.</p>'))
    }

    if (name === 'log') {
      parts.push(section('Assessment log', `
        <table class="log"><thead><tr>
          <th>Factor</th><th>Source</th><th>Status</th><th>Assessed</th>
        </tr></thead><tbody>
          ${b.log.map((r) => `<tr>
            <td>${escapeHtml(r.name)}</td>
            <td>${escapeHtml(r.source)}</td>
            <td>${escapeHtml(r.status.replace(/_/g, ' '))}${r.verified ? ' · live' : ''}</td>
            <td class="dim">${escapeHtml(formatDate(r.at))}</td>
          </tr>`).join('')}
        </tbody></table>`))
    }

    if (name === 'methodology') {
      parts.push(section('Methodology and provenance', `
        ${b.methodology.historical.version
          ? `<p>Historical metrics computed under method
             <code>${escapeHtml(String(b.methodology.historical.version))}</code>.</p>` : ''}
        <p class="note">${escapeHtml(b.methodology.limits)}</p>
        ${list(b.methodology.attributions)}`))
    }
  }

  // The document carries its own terms: it travels away from the app, and the
  // recipient never saw the screen this sentence normally lives on.
  parts.push(`<footer class="principle">
      <h2>The Contour principle</h2>
      <p>${escapeHtml(b.principle)}</p>
    </footer>`)

  return parts.join('\n')
}

/**
 * Open the Brief as its own document.
 *
 * A new window rather than a download, for the same reason the printable
 * report uses one: the user needs to *read it* before deciding to send it, and
 * a file that lands in Downloads is a file nobody checked. Print-to-PDF from
 * there is the browser's job and it does it better than we would.
 *
 * The stylesheet is inlined because this window has no build step behind it
 * and the document has to survive being saved to disk and mailed on.
 */
export function openBriefWindow(bodyHtml: string, siteName: string): void {
  const w = window.open('', '_blank')
  if (!w) return
  w.document.write(`<!doctype html><html><head><meta charset="utf-8">
    <title>Site investigation brief — ${escapeHtml(siteName)}</title>
    <style>${BRIEF_CSS}</style></head><body>${bodyHtml}</body></html>`)
  w.document.close()
}

/**
 * Document styling, deliberately austere.
 *
 * Field-notebook rather than dashboard: one column, generous measure, no
 * cards, no colour used to mean anything. Colour that encodes severity in a
 * document is a legend the reader does not have, and a red block beside a
 * finding reads as a verdict — which is precisely what the text beside it is
 * trying not to be.
 */
const BRIEF_CSS = `
  :root { --ink:#1a1f24; --dim:#5c666f; --line:#d8dcdf; --paper:#fff; }
  * { box-sizing: border-box; }
  body {
    margin: 0 auto; padding: 48px 36px 72px; max-width: 47em; background: var(--paper);
    color: var(--ink); font: 15px/1.65 ui-serif, Georgia, "Times New Roman", serif;
  }
  .kicker {
    margin: 0 0 6px; font: 600 11px/1 ui-sans-serif, system-ui, sans-serif;
    letter-spacing: .14em; text-transform: uppercase; color: var(--dim);
  }
  h1 { margin: 0 0 6px; font-size: 27px; line-height: 1.2; letter-spacing: -.01em; }
  .sub { margin: 0; color: var(--dim);
         font: 12.5px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace; }
  .head { padding-bottom: 20px; border-bottom: 2px solid var(--ink); margin-bottom: 28px; }
  .s { margin: 0 0 30px; }
  h2 {
    margin: 0 0 12px; font: 600 11px/1 ui-sans-serif, system-ui, sans-serif;
    letter-spacing: .14em; text-transform: uppercase; color: var(--dim);
    padding-bottom: 7px; border-bottom: 1px solid var(--line);
  }
  h3 { margin: 0 0 6px; font-size: 17px; }
  h4 {
    margin: 0 0 5px; font: 600 10px/1 ui-sans-serif, system-ui, sans-serif;
    letter-spacing: .1em; text-transform: uppercase; color: var(--dim);
  }
  p { margin: 0 0 9px; }
  .lead { font-size: 16px; }
  .note { color: var(--dim); font-size: 13px; font-style: italic; }
  .dim { color: var(--dim); font-size: 12.5px; }
  table { width: 100%; border-collapse: collapse; margin: 0 0 10px; font-size: 13.5px; }
  th { text-align: left; font-weight: 400; color: var(--dim); }
  .kv th, .kv td, .rows th, .rows td { padding: 5px 0; border-bottom: 1px solid var(--line); }
  .kv td, .rows td { text-align: right; }
  .rows td:first-of-type { text-align: left; }
  .log th, .log td { padding: 5px 8px 5px 0; border-bottom: 1px solid var(--line);
                     font-size: 12.5px; vertical-align: top; }
  .log thead th { font: 600 10px/1 ui-sans-serif, system-ui, sans-serif;
                  letter-spacing: .08em; text-transform: uppercase; }
  .finding { margin: 0 0 26px; padding-left: 15px; border-left: 2px solid var(--ink); }
  .fnum { margin: 0; font: 600 11px/1 ui-monospace, monospace; color: var(--dim); }
  .fthresh { font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--dim); }
  /* Equal weight, side by side. Setting the limitation smaller than the claim
     would reproduce in CSS the exact misreading the section exists to stop. */
  .claims { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin: 12px 0 8px; }
  .claims p { font-size: 13.5px; margin: 0 0 6px; }
  .claims > div { padding: 11px 13px; border: 1px solid var(--line); }
  .prompt { font-size: 13.5px; }
  .gap { margin: 0 0 12px; }
  .principle { margin-top: 40px; padding-top: 18px; border-top: 2px solid var(--ink); }
  .principle p { font-size: 16px; }
  ul { margin: 0; padding-left: 18px; color: var(--dim); font-size: 12.5px; }
  @media print {
    body { padding: 0; max-width: none; }
    .s, .finding { break-inside: avoid; }
    h2 { break-after: avoid; }
  }
`
