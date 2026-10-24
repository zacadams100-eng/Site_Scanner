import { useStore } from '../store'
import { formatRadius } from '../lib/format'

// Shared, so the selector returns the same array every render (a fresh [] loops).
const NO_GROUPS: string[] = []

/** Before anything is drawn: what a sheet will search, and how far. */
export default function LayerList() {
  const layers = useStore((s) => s.layers)
  const groups = useStore((s) => s.info?.groups ?? NO_GROUPS)
  return (
    <div className="layer-list">
      {groups.map((g) => (
        <section key={g} className="finding-group">
          <h3 className="group-title">{g}</h3>
          {layers.filter((l) => l.group === g).map((l) => (
            <div key={l.id} className="layer-row">
              <span className="layer-name">{l.name}</span>
              <span className="layer-pub">{l.publisher}</span>
              <span className="finding-radius">{formatRadius(l.search_m)}</span>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}
