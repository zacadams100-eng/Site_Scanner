import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import { PLACES_ATTRIBUTION, searchPlaces, withinCoverage, type Place } from '../lib/places'

/**
 * "Where is my site?" — the question the app could not answer.
 *
 * The map opened near Guildford and the only way to reach anywhere else was to
 * pan. That makes the drawing tools unreachable for anyone who cannot navigate
 * an unlabelled, desaturated basemap by eye, which is most people.
 *
 * Deliberately not a filter over the data: this moves the map and nothing
 * else. Searching for a place does not draw an area or run a query, because
 * guessing a boundary from a place name is exactly the kind of invented
 * precision this project refuses everywhere else.
 */
export default function PlaceSearch() {
  const goTo = useStore((s) => s.goTo)
  const catalog = useStore((s) => s.catalog)

  const [q, setQ] = useState('')
  const [results, setResults] = useState<Place[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const wrapRef = useRef<HTMLDivElement>(null)

  // Debounced, and every in-flight lookup is abandoned when the next keystroke
  // arrives — otherwise a slow answer for "gui" lands on top of "guildford".
  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) { setResults([]); setError(null); setBusy(false); return }
    const ctrl = new AbortController()
    setBusy(true)
    const timer = setTimeout(() => {
      searchPlaces(term, ctrl.signal)
        .then((r) => {
          if (ctrl.signal.aborted) return
          setResults(r)
          setCursor(0)
          setError(r.length ? null : 'Nothing found. Try a postcode, or "51.235, -0.57".')
        })
        .catch((e) => {
          if (ctrl.signal.aborted || e?.name === 'AbortError') return
          setResults([])
          setError(e?.message ?? 'Lookup failed.')
        })
        .finally(() => { if (!ctrl.signal.aborted) setBusy(false) })
    }, 300)
    return () => { clearTimeout(timer); ctrl.abort() }
  }, [q])

  // Clicking anywhere else closes the list, which is the behaviour every other
  // search box on the machine has.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    return () => window.removeEventListener('mousedown', onDown)
  }, [])

  const choose = (p: Place) => {
    goTo(p.lng, p.lat, p.zoom)
    setOpen(false)
    setQ(p.name)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { setCursor((c) => Math.min(results.length - 1, c + 1)); e.preventDefault() }
    else if (e.key === 'ArrowUp') { setCursor((c) => Math.max(0, c - 1)); e.preventDefault() }
    else if (e.key === 'Enter' && results[cursor]) { choose(results[cursor]); e.preventDefault() }
    else if (e.key === 'Escape') { setOpen(false); e.preventDefault() }
  }

  const bbox = catalog?.coverage.bbox
  const showList = open && (results.length > 0 || !!error || busy)

  return (
    <div className="place-search" ref={wrapRef}>
      <svg className="place-icon" viewBox="0 0 16 16" width="13" height="13" fill="none"
           stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden>
        <circle cx="7" cy="7" r="4.5" /><path d="M10.4 10.4L14 14" />
      </svg>
      <input
        className="place-input"
        value={q}
        placeholder="Find a place or postcode"
        aria-label="Find a place or postcode"
        role="combobox"
        aria-expanded={showList}
        aria-controls="place-results"
        onChange={(e) => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {q && (
        <button className="place-clear" aria-label="Clear search"
                onClick={() => { setQ(''); setResults([]); setError(null) }}>×</button>
      )}

      {showList && (
        <div className="place-results" id="place-results" role="listbox">
          {busy && !results.length && <div className="place-note">Searching…</div>}
          {error && !busy && <div className="place-note place-note-error">{error}</div>}
          {results.map((p, i) => {
            const outside = bbox ? !withinCoverage(p, bbox) : false
            return (
              <button
                key={p.id}
                role="option"
                aria-selected={i === cursor}
                className={`place-row${i === cursor ? ' is-cursor' : ''}`}
                onMouseEnter={() => setCursor(i)}
                onClick={() => choose(p)}
              >
                <span className="place-name">{p.name}</span>
                <span className="place-detail">
                  {p.detail}
                  {/* Coverage is England only, so a Cardiff result has to say
                      so before the user draws there and gets a 400 back. */}
                  {outside && <em className="place-outside"> · outside coverage</em>}
                </span>
              </button>
            )
          })}
          {!!results.length && results[0].kind !== 'coords' && (
            <div className="place-attrib">{PLACES_ATTRIBUTION}</div>
          )}
        </div>
      )}
    </div>
  )
}
