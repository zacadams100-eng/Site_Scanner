import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Self-hosted rather than fetched from a font CDN: the published build runs
// under a strict content policy, an offline Cloud Shell session has to render
// the same, and a webfont that silently fails to load takes the brand with it.
// Only the weights actually used are imported — each one is a file.
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'

import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
