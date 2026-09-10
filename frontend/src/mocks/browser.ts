import { setupWorker } from 'msw/browser'

import { api } from '@/lib/api'
import { handlers } from '@/mocks/handlers'
import { invalidateRemote, isRemoteCollection } from '@/mocks/userDirectory'

export const worker = setupWorker(...handlers)

/**
 * Keep the mock server's view of the backend-served collections fresh.
 *
 * Writes to /api/users and /api/accounts go straight through to FastAPI, so the
 * directory MSW caches to join names onto OTHER modules' list rows never hears
 * about them. Without this, renaming an account leaves the old name showing on
 * every lead that points at it until the cache expires.
 *
 * Registered here rather than in src/lib/api.ts so that production code carries
 * no knowledge of the mock layer: this file is only ever loaded when mocking is
 * enabled. It watches the one Axios client every component already uses, so it
 * catches every writer — the record editor, the create screens, and the Lead's
 * account write-back in LeadAccountFieldSync.
 */
api.interceptors.response.use((response) => {
  const method = (response.config.method ?? 'get').toLowerCase()
  if (method === 'get') return response

  // config.url is relative to the client's '/api' baseURL — '/accounts/ACC-001'.
  const collection = (response.config.url ?? '').replace(/^\/+/, '').split(/[/?]/)[0]
  if (isRemoteCollection(collection)) invalidateRemote(collection)

  return response
})
