/**
 * Analytics — the architecture, deliberately inert.
 *
 * Two gates, and it does nothing unless **both** are open:
 *
 * 1. `VITE_GA_MEASUREMENT_ID` is configured. No id is hard-coded here and none
 *    should be: the real one belongs in the deployment environment, and a
 *    measurement id committed to a public repository is a measurement id
 *    anyone can pollute.
 * 2. The visitor has consented. Under UK GDPR and PECR, analytics cookies need
 *    consent before they are set, not after — so `enable()` must be called by a
 *    consent mechanism, and there is no default-on path.
 *
 * **There is no consent UI yet, so analytics is off in every environment.**
 * That is the correct state rather than an oversight: shipping a tracker with
 * a "we'll add the banner later" is the version that breaks the law, and this
 * product's whole argument is that it does not quietly do things it has not
 * said it does.
 *
 * ## Configuring the real id
 *
 *     # .env.local, or the deployment's environment
 *     VITE_GA_MEASUREMENT_ID=G-XXXXXXXXXX
 *
 * Vite inlines `VITE_`-prefixed variables at build time, so this is a build
 * input rather than a runtime secret — which is correct for a measurement id
 * and wrong for anything else. Do not put a key here that must stay private.
 *
 * ## What still needs deciding
 *
 * - whether analytics is wanted at all
 * - the consent mechanism, and whether it is essential-only by default
 * - what is measured, and the retention period the privacy policy states
 *
 * See `docs/WEBSITE_AUDIT.md`.
 */

let consented = false

/** The configured id, or empty when analytics has not been set up. */
export function measurementId(): string {
  return (import.meta.env?.VITE_GA_MEASUREMENT_ID as string | undefined) ?? ''
}

/** Whether analytics would actually run: configured **and** consented. */
export function isActive(): boolean {
  return Boolean(measurementId()) && consented
}

/**
 * Record consent. Called by a consent mechanism that does not exist yet.
 *
 * Separate from configuration on purpose: an id being present must never be
 * read as permission to use it.
 */
export function setConsent(granted: boolean): void {
  consented = granted
}

/**
 * Send an event, if analytics is active.
 *
 * A no-op otherwise, and silently so — a console warning on every page load of
 * a deployment that has deliberately not configured analytics is noise, not a
 * signal.
 */
export function track(event: string, params: Record<string, unknown> = {}): void {
  if (!isActive()) return
  const gtag = (window as unknown as { gtag?: (...a: unknown[]) => void }).gtag
  gtag?.('event', event, params)
}
