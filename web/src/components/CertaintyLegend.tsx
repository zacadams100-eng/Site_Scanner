import { useStore } from '../store'
import { labelStep } from '../lib/format'
import { certaintyOf, certaintyNote } from '../lib/uncertainty'

/**
 * What the hatching on the map means, shown only while there is hatching.
 *
 * A pattern with no key is decoration, and an unexplained one is worse than
 * none — the reader either ignores it or invents a meaning for it. This states
 * the case in words and carries the measured coverage, because a figure can be
 * checked against the table and an adjective cannot.
 *
 * It appears and disappears with the condition rather than sitting there
 * permanently. A legend for a state that is not currently true is noise, and
 * this interface is already carrying a lot of honest caveats; the ones that
 * are always on stop being read.
 */
export default function CertaintyLegend() {
  const data = useStore((s) => s.data)
  const selected = useStore((s) => s.selected)
  const timeIndex = useStore((s) => s.timeIndex)
  const cells = useStore((s) => s.cells)

  const series = data?.series[selected[0]]
  const point = series?.points[timeIndex]
  const certainty = certaintyOf(point)

  // Nothing drawn means nothing to qualify. Categorical factors are not
  // painted on the map at all, so they cannot be hatched either.
  if (!cells.length || !series || certainty === 'ok') return null
  if (series.meta.kind === 'categorical') return null

  const step = data?.steps?.[timeIndex]
  const note = certaintyNote(point, step ? labelStep(step) : undefined)
  if (!note) return null

  return (
    <div className={`certainty-key is-${certainty}`} role="note">
      <span className={`certainty-swatch is-${certainty}`} aria-hidden />
      <span className="certainty-text">{note}</span>
    </div>
  )
}
