type Item = Record<string, unknown>

/**
 * The collections MSW does NOT hold, fetched so it can still join their names.
 *
 * Most collections live in the Zustand store and are read synchronously. Users
 * and accounts do not — they are real database resources behind /api/users and
 * /api/accounts. But the list endpoint still has to join owner and account
 * NAMES onto rows of leads, contacts, quotes and registrations (see
 * lookupLabels() in query.ts), and it cannot read PostgreSQL synchronously from
 * inside a service worker.
 *
 * So the handler awaits this before running the query. Each fetch goes back out
 * through the passthrough handler registered for that path and on to FastAPI;
 * it does not re-enter the mock store.
 *
 * Cached briefly because one list request resolves labels for every lookup
 * field on the module at once, and a page of 25 rows must not become 25 round
 * trips. Administration and the Accounts screen invalidate it after a write, so
 * a rename does not keep showing the old name on a lead.
 */

const TTL_MS = 15_000

/** Collection name -> the endpoint that serves it. */
const REMOTE = {
  users: '/api/users',
  accounts: '/api/accounts',
  contacts: '/api/contacts',
  leads: '/api/leads',
  opportunities: '/api/opportunities',
  deals: '/api/deals',
} as const

export type RemoteCollection = keyof typeof REMOTE

export type RemoteDirectories = Record<RemoteCollection, Item[]>

interface Entry {
  rows: Item[]
  fetchedAt: number
  inFlight: Promise<Item[]> | null
}

const cache: Record<RemoteCollection, Entry> = {
  users: { rows: [], fetchedAt: 0, inFlight: null },
  accounts: { rows: [], fetchedAt: 0, inFlight: null },
  contacts: { rows: [], fetchedAt: 0, inFlight: null },
  leads: { rows: [], fetchedAt: 0, inFlight: null },
  opportunities: { rows: [], fetchedAt: 0, inFlight: null },
  deals: { rows: [], fetchedAt: 0, inFlight: null },
}

export function invalidateUserDirectory(): void {
  invalidateRemote('users')
}

export function invalidateRemote(collection?: RemoteCollection): void {
  const names = collection ? [collection] : (Object.keys(REMOTE) as RemoteCollection[])
  for (const name of names) {
    cache[name].rows = []
    cache[name].fetchedAt = 0
  }
}

/** True for a collection served by the real backend rather than the store. */
export function isRemoteCollection(name: string): name is RemoteCollection {
  return name in REMOTE
}

function fetchOne(name: RemoteCollection): Promise<Item[]> {
  const entry = cache[name]

  if (entry.fetchedAt && Date.now() - entry.fetchedAt < TTL_MS) {
    return Promise.resolve(entry.rows)
  }

  // Collapse concurrent list requests onto one fetch — a screen with two lists
  // on it would otherwise ask twice for the same directory.
  if (entry.inFlight) return entry.inFlight

  entry.inFlight = (async () => {
    try {
      // The list endpoint pages by default for accounts only when asked, so no
      // parameters here: the label join needs every row, not the first page.
      const response = await fetch(REMOTE[name])
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const rows = (await response.json()) as Item[]
      entry.rows = Array.isArray(rows) ? rows : []
      entry.fetchedAt = Date.now()
    } catch (error) {
      // The backend being down must not take the whole prototype with it. Keep
      // the last good rows if there are any; otherwise resolve to nothing, and
      // the column falls back to showing the raw id rather than failing the
      // list request outright.
      console.warn(`[mocks] ${name} directory unavailable — names will show as ids`, error)
    } finally {
      entry.inFlight = null
    }
    return entry.rows
  })()

  return entry.inFlight
}

/** Every remote collection, for the list endpoint's label join. */
export async function remoteDirectories(): Promise<RemoteDirectories> {
  const names = Object.keys(REMOTE) as RemoteCollection[]
  const results = await Promise.all(names.map(fetchOne))
  return Object.fromEntries(names.map((n, i) => [n, results[i]])) as RemoteDirectories
}

/** Back-compat for callers that only wanted users. */
export async function userDirectory(): Promise<Item[]> {
  return fetchOne('users')
}
