import bundledFields from '../../../spec/fields.json'
import bundledPicklists from '../../../spec/picklists.json'
import bundledStages from '../../../spec/stages.json'

/**
 * WHERE THE REGISTER COMES FROM: the server first, the built-in copy second.
 *
 * Decided 21 Sep 2026: a change published in Administration reaches the live
 * app with no rebuild. So before anything else loads, main.tsx asks
 * GET /api/spec for the latest PUBLISHED fields, picklists and stages, and
 * every module that reads the register (lib/spec/index.ts, lib/pipeline.ts)
 * reads them from here. The server's required-field check reads the same
 * version (backend/app/requirements.py), so the red asterisk and the save
 * that refuses agree.
 *
 * The copy built from spec/*.json is the fallback, not a second truth: it is
 * what the sign-in page and "Access pending" run on (no session, so no
 * /api/spec), and what the app runs on if the request fails.
 *
 * Read once. A publish reaches a browser already open on its next page load.
 */
export const specSource: {
  fields: unknown
  picklists: unknown
  stages: unknown
  /** The published version in use, or null for the built-in copy. */
  version: number | null
} = {
  fields: bundledFields,
  picklists: bundledPicklists,
  stages: bundledStages,
  version: null,
}

interface PublishedSpec {
  version: number
  fields: unknown[]
  picklists: Record<string, unknown>
  stages: unknown[]
}

function isPublishedSpec(value: unknown): value is PublishedSpec {
  const v = value as PublishedSpec | null
  return Boolean(v) && Array.isArray(v!.fields) && Array.isArray(v!.stages) && typeof v!.picklists === 'object'
}

/**
 * Plain fetch, not the Axios client: that client's interceptors send a 401 to
 * the sign-in page, and a visitor who is not signed in yet must simply get the
 * built-in copy.
 */
export async function loadPublishedSpec(): Promise<void> {
  try {
    const response = await fetch('/api/spec', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    if (response.status !== 200) return
    const doc: unknown = await response.json()
    if (!isPublishedSpec(doc)) return
    specSource.fields = doc.fields
    specSource.picklists = doc.picklists
    specSource.stages = doc.stages
    specSource.version = doc.version
  } catch {
    // Offline, server restarting: the built-in copy still renders every form.
  }
}
