import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes as RouterRoutes } from 'react-router-dom'
import {
  About, CaseStudies, CoastalScanner, Contact, HabitatScanner, Home, LandScanner,
  NotFound,
  Privacy, RequestScan, Scanners, ThankYou,
} from './site/Pages'
import { APP_PATH, PAGES } from './site/site'

/**
 * The application is loaded on demand.
 *
 * It carries MapLibre, seven turf modules and Observable Plot — a GIS engine,
 * a geometry library and a plotting library, none of which a marketing page
 * uses. Statically imported they landed in the single entry chunk, so someone
 * reading the About page downloaded a map renderer to read prose.
 *
 * The split is drawn here rather than deeper because it matches the one real
 * boundary in this codebase: the public site and the application share a brand
 * and nothing else.
 */
const App = lazy(() => import('./App'))

/** Deliberately close to nothing.
 *
 *  This shows for the few hundred milliseconds of a chunk fetch, and the
 *  application renders its own considered loading sequence immediately
 *  afterwards. A second spinner before that one would be a flash of
 *  furniture, not reassurance. */
function AppLoading() {
  return <div className="app-boot" role="status" aria-label="Loading the scanner" />
}

/**
 * The two experiences, kept apart.
 *
 *     /            marketing — explains the product, converts
 *     /app         application — scanner library, then the workspace
 *
 * They share a brand and nothing else: no chrome, no navigation, no layout.
 * Merging them would blur the line between reading about a scanner and running
 * one, which is the specific confusion this split exists to prevent.
 *
 * The application is one route with everything below it in the URL fragment —
 * a drawn shape, a chosen scanner, an open investigation. That is deliberate:
 * a fragment never reaches the server, so an assessment cannot be
 * reconstructed from server logs, and there is nothing under `/app` for a
 * crawler to index.
 */
export default function Routes() {
  return (
    <BrowserRouter>
      <RouterRoutes>
        <Route path={PAGES.home.path} element={<Home />} />
        <Route path={PAGES.scanners.path} element={<Scanners />} />
        <Route path={PAGES.land.path} element={<LandScanner />} />
        <Route path={PAGES.habitat.path} element={<HabitatScanner />} />
        <Route path={PAGES.coastal.path} element={<CoastalScanner />} />
        <Route path={PAGES.about.path} element={<About />} />
        <Route path={PAGES.caseStudies.path} element={<CaseStudies />} />
        <Route path={PAGES.contact.path} element={<Contact />} />
        <Route path={PAGES.request.path} element={<RequestScan />} />
        <Route path={PAGES.thanks.path} element={<ThankYou />} />
        <Route path={PAGES.privacy.path} element={<Privacy />} />

        <Route path={`${APP_PATH}/*`}
               element={<Suspense fallback={<AppLoading />}><App /></Suspense>} />

        <Route path="*" element={<NotFound />} />
      </RouterRoutes>
    </BrowserRouter>
  )
}
