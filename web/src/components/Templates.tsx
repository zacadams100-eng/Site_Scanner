import { useStore } from '../store'
import { TEMPLATES } from '../lib/permalink'

/**
 * Guided starting points.
 *
 * The target user knows GIS concepts but not this interface. A template is a
 * worked example that produces their answer on the first visit, which is the
 * whole onboarding problem solved without a tutorial — and it is why an open
 * 118-factor catalogue does not have to be intimidating on day one.
 */
export default function Templates() {
  const open = useStore((s) => s.templatesOpen)
  const setOpen = useStore((s) => s.setTemplatesOpen)
  const applyTemplate = useStore((s) => s.applyTemplate)
  const catalog = useStore((s) => s.catalog)
  const aoi = useStore((s) => s.aoi)

  if (!open) return null

  const nameFor = (id: string) =>
    catalog?.factors.find((f) => f.id === id)?.name ?? id

  return (
    <div className="modal-scrim" onClick={() => setOpen(false)}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="modal-title">Start from a question</div>
            <div className="modal-sub">
              Each one picks the right factors for you. {aoi
                ? 'Your drawn shape stays as it is.'
                : 'Then draw a shape on the map.'}
            </div>
          </div>
          <button className="browser-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
        </div>

        <div className="template-grid">
          {TEMPLATES.map((t) => (
            <button key={t.id} className="template" onClick={() => applyTemplate(t)}>
              <div className="template-name">{t.name}</div>
              <div className="template-blurb">{t.blurb}</div>
              <div className="template-factors">
                {t.factors.map((f) => (
                  <span key={f} className="template-chip">{nameFor(f)}</span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
