import { http, HttpResponse, delay } from 'msw'

import { runListQuery } from '@/mocks/query'
import { useDataStore } from '@/store/useDataStore'

// Artificial latency so loading states in the UI are visible and realistic,
// same as a real backend call would be.
const LATENCY_MS = 150

export const handlers = [
  // Filtering, sorting and paging are query parameters on the collection, not
  // work the caller does after the fact — see src/mocks/query.ts. A request
  // with no parameters still returns the whole collection, so a lookup
  // combobox reads the same endpoint as a paged list screen.
  http.get('/api/:module', async ({ params, request }) => {
    await delay(LATENCY_MS)
    const collection = params.module as string
    const data = useDataStore.getState().list(collection)
    if (!Array.isArray(data)) return HttpResponse.json(data ?? [])

    const { rows, total } = runListQuery(collection, data as Record<string, unknown>[], new URL(request.url))
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
    const body = (await request.json()) as Record<string, unknown>
    const updated = useDataStore.getState().update(params.module as string, params.id as string, body)
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
