import { useEffect, useRef } from 'react'
import { useStore } from '../store'
import { TEMPLATES } from '../lib/permalink'
import { useEscape } from '../lib/useEscape'

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
  const closeRef = useRef<HTMLButtonElement>(null)

  useEscape(open, () => setOpen(false))

  // Focus moves into the dialog when it opens. Without this a keyboard user
  // opening it from the toolbar is still focused behind the scrim, and tabs
  // through the whole map before reaching a card.
  useEffect(() => {
    if (open) closeRef.current?.focus()
  }, [open])

  if (!open) return null

  const nameFor = (id: string) =>
    catalog?.factors.find((f) => f.id === id)?.name ?? id

  return (
    <div className="modal-scrim" onClick={() => setOpen(false)}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="templates-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <div className="modal-title" id="templates-title">Start from a question</div>
            <div className="modal-sub">
              Each one picks the right factors for you. {aoi
                ? 'Your drawn shape stays as it is.'
                : 'Then draw a shape on the map.'}
            </div>
          </div>
          <button ref={closeRef} className="browser-close" onClick={() => setOpen(false)} aria-label="Close">×</button>
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
