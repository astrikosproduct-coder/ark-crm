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

/** How long to wait for the mock service worker before drawing the app anyway. */
const MOCK_START_TIMEOUT_MS = 5000

/**
 * Start the mock API, but never let it decide whether the app renders.
 *
 * This used to be `enableMocking().then(render)`. A service worker that failed
 * to register — evicted by the browser, a stale registration after a deploy, a
 * tab restored from days ago — rejected that promise, nothing was ever
 * rendered, and the app was simply a blank page until a hard refresh happened
 * to catch a good registration. That is the "goes blank, refresh fixes it"
 * failure.
 *
 * Now a worker that fails or hangs costs API responses, which surface as
 * ordinary per-screen error states, rather than the entire UI.
 */
async function startMocking(): Promise<void> {
  try {
    const { worker } = await import('@/mocks/browser')
    await Promise.race([
      worker.start({
        onUnhandledRequest: 'bypass',
        serviceWorker: { url: '/mockServiceWorker.js' },
      }),
      new Promise((resolve) => setTimeout(resolve, MOCK_START_TIMEOUT_MS)),
    ])
  } catch (error) {
    console.error('[msw] the mock API did not start; the app will render without it:', error)
  }
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
  // Drafts used to be kept in localStorage under this key. They are gone as a
  // concept — unsaved work is now confirmed, never quietly stored — so any left
  // in a browser from a previous version are cleared out rather than orphaned.
  localStorage.removeItem('arkcrm-drafts')

  void startMocking().finally(() => {
    root.render(
      <StrictMode>
        <ErrorBoundary>
          <QueryClientProvider client={queryClient}>
            <App />
          </QueryClientProvider>
        </ErrorBoundary>
      </StrictMode>
    )
  })
}
