import { http, HttpResponse, delay, passthrough } from 'msw'

import { runListQuery } from '@/mocks/query'
import { remoteDirectories } from '@/mocks/userDirectory'
import { useDataStore } from '@/store/useDataStore'

// Artificial latency so loading states in the UI are visible and realistic,
// same as a real backend call would be.
const LATENCY_MS = 150

export const handlers = [
  /**
   * Sign-in, and FIRST of all — every other handler below now depends on the
   * session this one establishes. /api/auth/login and /api/auth/callback are
   * browser navigations rather than fetches, so MSW would not see them anyway;
   * /api/auth/me is a real request from the app and must reach FastAPI.
   */
  http.all('/api/auth/*', () => passthrough()),

  /**
   * Administration is the first real database-backed module: it is served by
   * FastAPI over PostgreSQL, not from the store. This handler must stay FIRST —
   * MSW matches in order, and the catch-alls below would otherwise swallow
   * /api/admin/users as `{ module: 'admin', id: 'users' }` and answer 404.
   *
   * passthrough() lets the request continue to the network, where Vite's dev
   * proxy (see vite.config.ts) forwards /api/admin to localhost:8000. Every
   * other /api/* path is untouched and still answered from the store below.
   */
  http.all('/api/admin/*', () => passthrough()),

  /**
   * Users are a real database resource, not a mock collection. Every
   * user-lookup field in the application — 27 of them across nine modules —
   * reads /api/users, and it now reaches FastAPI rather than the store.
   *
   * These two must also stay ABOVE the catch-alls. Note the list endpoint's
   * label join no longer finds users in the store either; see
   * lookupLabels() in src/mocks/query.ts, which is handed the directory.
   */
  http.all('/api/users', () => passthrough()),
  http.all('/api/users/*', () => passthrough()),

  /**
   * Accounts, the second real database-backed module. Both End Clients and
   * Partners are rows in the one accounts table, so the Partners screen — which
   * is a filtered VIEW over this collection, not one of its own — passes
   * through here too.
   *
   * FastAPI implements the same list contract this file's catch-all does:
   * repeated-parameter OR filters, q, _sort/_order, _page/_limit,
   * X-Total-Count and the __labels join. See backend/app/routers/accounts.py.
   */
  http.all('/api/accounts', () => passthrough()),
  http.all('/api/accounts/*', () => passthrough()),

  /**
   * Contacts, the third and final Round-1 table. The external people at those
   * accounts — internal employees are users, and the two never mix.
   */
  http.all('/api/contacts', () => passthrough()),
  http.all('/api/contacts/*', () => passthrough()),

  /**
   * The three pipeline modules — Phase-1 cutover. Their FastAPI routers
   * (backend/app/routers/{leads,opportunities,deals}.py) implement the same
   * list contract this file's catch-all does, so no caller changed: same
   * paths, same payload shapes, answered from PostgreSQL instead of the
   * browser store.
   *
   * This also closes a real gap. /transitions and /conversions were already
   * passed through below, so every conversion was writing an audit row to
   * PostgreSQL that referenced a Lead/Opportunity/Deal id existing only in
   * that browser's localStorage. Both ends live in the same database now.
   */
  http.all('/api/leads', () => passthrough()),
  http.all('/api/leads/*', () => passthrough()),
  http.all('/api/opportunities', () => passthrough()),
  http.all('/api/opportunities/*', () => passthrough()),
  http.all('/api/deals', () => passthrough()),
  http.all('/api/deals/*', () => passthrough()),

  /**
   * Stage transitions and conversions, Round 7's first cutover. Both used to
   * be answered by the generic catch-all below, from the `transitions` and
   * `conversions` collections in the browser store — see
   * AdvanceStageDialog.tsx, LeadAdvanceDialog.tsx, DealDetailPage.tsx (the
   * former) and opportunities/ConvertToDealDialog.tsx (the latter). Those
   * callers are unchanged: same paths, same payload shapes, now answered by
   * backend/app/routers/transitions.py and conversions.py instead.
   */
  http.all('/api/transitions', () => passthrough()),
  http.all('/api/transitions/*', () => passthrough()),
  http.all('/api/conversions', () => passthrough()),
  http.all('/api/conversions/*', () => passthrough()),

  /**
   * Deal registrations and their conflict adjudications, Round 3 (done out of
   * order, after Round 7). Same story: NewRegistrationPage.tsx,
   * RegistrationDetailPage.tsx, ConflictPanel.tsx and
   * opportunities/../leads/ConvertToDealDialog.tsx already speak these paths
   * against the mock store's `registrations`/`conflicts` collections. Now
   * answered by backend/app/routers/registrations.py and conflicts.py.
   */
  http.all('/api/registrations', () => passthrough()),
  http.all('/api/registrations/*', () => passthrough()),
  http.all('/api/conflicts', () => passthrough()),
  http.all('/api/conflicts/*', () => passthrough()),

  // Filtering, sorting and paging are query parameters on the collection, not
  // work the caller does after the fact — see src/mocks/query.ts. A request
  // with no parameters still returns the whole collection, so a lookup
  // combobox reads the same endpoint as a paged list screen.
  http.get('/api/:module', async ({ params, request }) => {
    await delay(LATENCY_MS)
    const collection = params.module as string
    const data = useDataStore.getState().list(collection)
    if (!Array.isArray(data)) return HttpResponse.json(data ?? [])

    // Owner and account names are joined onto the page from the real backend,
    // which is a fetch rather than a store read now that users and accounts
    // live in PostgreSQL.
    const remote = await remoteDirectories()

    const { rows, total } = runListQuery(
      collection,
      data as Record<string, unknown>[],
      new URL(request.url),
      remote
    )
    return HttpResponse.json(rows, { headers: { 'X-Total-Count': String(total) } })
  }),

  http.post('/api/:module', async ({ params, request }) => {
    await delay(LATENCY_MS)
    const body = (await request.json()) as Record<string, unknown>
    const created = useDataStore.getState().create(params.module as string, body)
    if (!created) {
      return HttpResponse.json({ message: `"${params.module}" is not a writable collection` }, { status: 400 })
    }
    return HttpResponse.json(created, { status: 201 })
  }),

  http.get('/api/:module/:id', async ({ params }) => {
    await delay(LATENCY_MS)
    const item = useDataStore.getState().getById(params.module as string, params.id as string)
    if (!item) return HttpResponse.json({ message: 'Not found' }, { status: 404 })
    return HttpResponse.json(item)
  }),

  http.put('/api/:module/:id', async ({ params, request }) => {
    await delay(LATENCY_MS)
    const collection = params.module as string
    const id = params.id as string
    const body = (await request.json()) as Record<string, unknown>

    const updated = useDataStore.getState().update(collection, id, body)
    if (!updated) return HttpResponse.json({ message: 'Not found' }, { status: 404 })
    return HttpResponse.json(updated)
  }),

  http.delete('/api/:module/:id', async ({ params }) => {
    await delay(LATENCY_MS)
    const ok = useDataStore.getState().remove(params.module as string, params.id as string)
    if (!ok) return HttpResponse.json({ message: 'Not found' }, { status: 404 })
    return new HttpResponse(null, { status: 204 })
  }),
]
