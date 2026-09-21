import { api } from '@/lib/api'
import { catalogueCollection, isCatalogueCollection } from '@/lib/catalogue'

type Row = Record<string, unknown>

/**
 * Collections that a live form can point a lookup at, but that no module
 * serves yet: Quotes, the three Gates, Bids and POCs are all "coming in a later
 * phase". There is nothing to choose, so a lookup onto one offers an empty list
 * — without a request, because the server has no such endpoint and asking would
 * only turn an honest "nothing here yet" into an error on the form.
 *
 * When one of these modules is built and served by FastAPI, delete it from
 * this set and its lookups start reading from the server with no other change.
 */
const NOT_BUILT = new Set(['quotes', 'gates', 'bids', 'pocs'])

/**
 * Every row of a collection a lookup, filter or picker reads.
 *
 * The one place that decides WHERE a collection comes from:
 *   · the catalogue (products, the price book) — bundled, no request
 *   · a module not built yet                    — empty, no request
 *   · everything else                           — GET /api/<collection>
 *
 * Every caller shares the query key ['collection', collection], so a screen
 * that has already opened one lookup pays nothing for the next.
 */
export async function fetchCollection<T extends Row = Row>(collection: string): Promise<T[]> {
  if (isCatalogueCollection(collection)) return (catalogueCollection(collection) as T[]) ?? []
  if (NOT_BUILT.has(collection)) return []
  return (await api.get<T[]>(`/${collection}`)).data
}

/**
 * The only collections a lookup may offer "+ Create new" for: a new Account or
 * Contact made in place, and a new Lead (which opens the Lead form).
 *
 * An allowlist, because everything else is created some other way and a quick
 * form would either fail or make something that should not exist:
 *   · users           Administration, from the Microsoft directory
 *   · opportunities,  born by conversion — one made from a lookup would have
 *     deals           no parent and no history
 *   · pursuit-groups  formed by the server when two pursuits collide
 *   · registrations   their own page, with the conflict check
 *   · products        the price book, edited as a file
 *   · quotes, gates,  not built yet
 *     bids, pocs
 */
const QUICK_CREATE = new Set(['accounts', 'contacts', 'leads'])

export function canCreateIn(collection: string | undefined): boolean {
  return Boolean(collection) && QUICK_CREATE.has(collection!)
}
