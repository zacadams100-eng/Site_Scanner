import { decodeState } from './permalink'

/**
 * Does the app open on the gallery, or on the map?
 *
 * The frame has two modes — gallery and workspace — and this decides which one
 * a visit starts in. It is a three-line function with a disproportionate effect
 * on whether anyone ever uses the product, so it lives here where it can be
 * tested rather than inside the store where it cannot.
 *
 * Two conditions send someone straight to the map, and each is sufficient
 * alone:
 *
 * - **No saved sites.** For a first-time user the gallery is pure obstacle.
 *   `docs/USER-TESTING.md` names seconds-until-they-draw-a-shape as the one
 *   measurement that decides this product, and a full window listing nothing
 *   spends those seconds on a wall that says "empty". A newcomer needs to see
 *   the map, because until there is a shape on it nothing else is reachable.
 * - **A shape in the URL.** A shared link is a specific site someone was sent.
 *   Opening *your* gallery in front of *their* site shows the wrong document
 *   to the one person guaranteed not to want it.
 *
 * Screen width is deliberately not a condition. A phone gets the gallery too —
 * arguably it needs it more, since a 390px map is harder to draw on than a
 * saved card is to tap.
 *
 * The result is not persisted. "Which mode was I in last Tuesday" is not state
 * anyone wants restored; the two honest answers are "show me my work" and
 * "here is the link I was sent", and both are computable at load.
 *
 * @param savedCount how many sites are in local storage
 * @param hash       `location.hash`, which may carry a shared site
 */
export function openOnGallery(savedCount: number, hash: string): boolean {
  if (savedCount <= 0) return false
  return !decodeState(hash).aoi
}
