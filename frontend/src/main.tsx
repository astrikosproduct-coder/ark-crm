import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'

import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from '@/components/layout/ErrorBoundary'
import { SpecStartupError } from '@/pages/SpecStartupError'
import { queryClient } from '@/lib/queryClient'
import { specRefErrors } from '@/lib/spec'
import { validateSpecExpressions } from '@/lib/spec/formula'

// Compile every expression in the spec before the first render. A typo in
// spec/extensions.json surfaces here, naming the field and the identifier,
// rather than as a field that silently never appears on a form.
const specProblems = validateSpecExpressions()
if (specProblems.length > 0) {
  console.error(
    `[spec] ${specProblems.length} expression(s) will not compile — see Spec health:`,
    specProblems
  )
}

const root = createRoot(document.getElementById('root')!)

/**
 * A sidecar entry naming a duplicated api_name stops the app here.
 *
 * Nine api_names are defined in two sections of one module. A reference like
 * "partners.partner" cannot say which is meant, and binding it to whichever the
 * register wrote last would put a plausible wrong field on a screen — the exact
 * failure this prototype exists to catch. Every other spec problem degrades
 * gracefully and lands on Spec Health; this one does not, because a screen
 * built on the wrong field looks entirely correct.
 */
if (specRefErrors.length > 0) {
  console.error(`[spec] ${specRefErrors.length} unresolvable reference(s) in spec/extensions.json:`)
  for (const message of specRefErrors) console.error(`  · ${message}`)
  root.render(
    <StrictMode>
      <SpecStartupError errors={specRefErrors} />
    </StrictMode>
  )
} else {
  clearPrototypeLeftovers()

  root.render(
    <StrictMode>
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </ErrorBoundary>
    </StrictMode>
  )
}

/**
 * What a browser that used the prototype may still be holding, removed on
 * every start (it costs nothing when there is nothing to remove).
 *
 *   arkcrm-data     the mock store — every record the prototype kept in the
 *                   browser. Removed with MSW on 21 Sep 2026: all data is in
 *                   PostgreSQL, and nothing business-related is stored here.
 *   arkcrm-drafts   unsaved form drafts, retired earlier — unsaved work is now
 *                   confirmed, never quietly stored.
 *   the mock service worker, which a browser keeps registered after the file
 *                   that installed it is gone. Left alone it sits between the
 *                   page and every request, so it is unregistered.
 *
 * Sidebar and theme preferences stay: they are one person's display settings,
 * not data.
 */
function clearPrototypeLeftovers(): void {
  try {
    localStorage.removeItem('arkcrm-data')
    localStorage.removeItem('arkcrm-drafts')
  } catch {
    // Storage blocked (private mode, policy) — then nothing was stored either.
  }
  if ('serviceWorker' in navigator) {
    void navigator.serviceWorker
      .getRegistrations()
      .then((registrations) =>
        registrations
          .filter((r) => (r.active ?? r.waiting ?? r.installing)?.scriptURL.endsWith('/mockServiceWorker.js'))
          .forEach((r) => void r.unregister())
      )
      .catch(() => undefined)
  }
}
