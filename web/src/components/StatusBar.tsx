import { useStore } from '../store'

/**
 * The instrument readout.
 *
 * Every GIS worth trusting tells you where the pointer is, how big the picture
 * is and which projection it is in, without being asked. It is the line that
 * separates a mapping tool from a picture of a map — and it is all measurement,
 * so all of it is set in mono.
 *
 * Deliberately the quietest thing on screen: 28px, one rule above it, no
 * colour except where a state is genuinely abnormal.
 *
 * On the home screen the readouts go away and only the connection state
 * stays. They describe a map, and on the gallery the map is behind an opaque
 * overlay — a scale bar and a zoom level for a picture nobody can see are not
 * quiet instruments, they are wrong ones, and "Cells 0" reads as a failure
 * rather than as "you have not opened anything".
 */
export default function StatusBar() {
  const cursor = useStore((s) => s.cursor)
  const view = useStore((s) => s.view)
  const cells = useStore((s) => s.cells)
  const data = useStore((s) => s.data)
  const isMock = useStore((s) => s.isMock)
  const catalogError = useStore((s) => s.catalogError)
  const loading = useStore((s) => s.loading)
  const home = useStore((s) => s.home)

  const live = data?.real_factors?.length ?? 0

  return (
    <footer className="statusbar">
      {!home && <>
        <span className="stat">
          <span className="stat-key">Lat</span>
          <span className="mono">{cursor ? cursor.lat.toFixed(5) : '—'}</span>
        </span>
        <span className="stat">
          <span className="stat-key">Lng</span>
          <span className="mono">{cursor ? cursor.lng.toFixed(5) : '—'}</span>
        </span>
        <span className="stat">
          <span className="stat-key">Scale</span>
          <span className="mono">{view ? `1:${Math.round(view.scale).toLocaleString('en-GB')}` : '—'}</span>
        </span>
        <span className="stat">
          <span className="stat-key">Zoom</span>
          <span className="mono">{view ? view.zoom.toFixed(2) : '—'}</span>
        </span>
        <span className="stat">
          <span className="stat-key">CRS</span>
          <span className="mono">EPSG:4326</span>
        </span>
        <span className="stat">
          <span className="stat-key">Cells</span>
          <span className="mono">{cells.length.toLocaleString('en-GB')}</span>
        </span>
      </>}

      <span className="stat stat-end">
        <span className={`conn-dot${catalogError ? ' is-bad' : isMock ? ' is-warn' : ''}`} aria-hidden />
        <span>
          {catalogError
            ? 'No connection to the API'
            : loading
              ? 'Reading…'
              : isMock
                ? 'Demo backend — generated data'
                : live > 0
                  ? `Connected · ${live} live layer${live === 1 ? '' : 's'}`
                  : 'Connected'}
        </span>
      </span>
    </footer>
  )
}
