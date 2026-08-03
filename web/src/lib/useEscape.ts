import { useEffect } from 'react'

/**
 * Escape closes the topmost dismissible layer.
 *
 * The interface stacks popovers over panels over the map, and a user who has
 * opened something expects one key to back out of it — whichever layer it was.
 * Listening on `window` rather than the element matters: focus is often still
 * on the trigger, which lives outside the layer being dismissed.
 *
 * `active` gates the listener rather than the caller gating the hook, so this
 * stays callable above an early return.
 */
export function useEscape(active: boolean, close: () => void) {
  useEffect(() => {
    if (!active) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      // Stop the event before a layer further out also treats it as a
      // dismissal — one press should close one thing.
      e.stopPropagation()
      close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, close])
}
