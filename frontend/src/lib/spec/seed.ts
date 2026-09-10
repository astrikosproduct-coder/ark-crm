import { addDays, differenceInCalendarDays, format, parseISO } from 'date-fns'

import { fieldsNamed, fieldsOf, movedRefs, resolvePicklistValue, seedNormalisationFor } from './index'
import { deriveOpportunitiesFromLeads } from './pipelineSeed'

type Item = Record<string, unknown>

/**
 * Bringing spec/seed/*.json onto the api_names in spec/fields.json.
 *
 * The two sides of the workbook disagree. The register sheets say the account
 * name field is `account_name` and the account type field is `account_type`;
 * the seed sheet writes `name` and `account_types`. The register says a contact
 * role is `DECM_DECISION_MAKER`; the seed writes `DECM`.
 *
 * Neither file may be hand-edited — build_spec.py overwrites both wholesale —
 * so the reconciliation is declared in spec/extensions.json (the one file here
 * that is hand-maintained) and applied once, here, as the store loads. Every
 * rule it applies is recorded and shown on the Spec Health page, because each
 * one is a defect somebody has to fix in the workbook.
 */

export interface SeedMismatch {
  collection: string
  api_name: string
  kind: 'renamed' | 'unresolved_value' | 'unknown_key' | 'moved_module'
  detail: string
}

const mismatches: SeedMismatch[] = []
let scanned = false

function note(m: SeedMismatch) {
  if (mismatches.some((x) => x.collection === m.collection && x.api_name === m.api_name && x.kind === m.kind)) {
    return
  }
  mismatches.push(m)
}

/** Normalise one record of one collection. Returns a new object. */
export function normaliseSeedRecord(collection: string, record: Item): Item {
  const spec = seedNormalisationFor(collection)
  if (!spec) return record

  const out: Item = {}

  for (const [key, value] of Object.entries(record)) {
    const renamed = spec.rename?.[key]
    if (renamed) {
      note({
        collection,
        api_name: key,
        kind: 'renamed',
        detail: `seed writes "${key}", the register calls it "${renamed}"`,
      })
    }
    out[renamed ?? key] = value
  }

  // Coerce every picklist-backed value to its key, so the Select and
  // MultiSelect controls have something they can match against.
  for (const field of fieldsOf(spec.module)) {
    if (field.type !== 'picklist' && field.type !== 'multiselect') continue
    const value = out[field.api_name]
    if (value === null || value === undefined || value === '') continue

    if (Array.isArray(value)) {
      out[field.api_name] = value.map((v) => {
        const { key, resolved } = resolvePicklistValue(field.picklist, v)
        if (!resolved) noteUnresolved(collection, field.api_name, field.picklist, v)
        return key
      })
    } else {
      const { key, resolved } = resolvePicklistValue(field.picklist, value)
      if (!resolved) noteUnresolved(collection, field.api_name, field.picklist, value)
      out[field.api_name] = key
    }
  }

  // Anything left over that the register has never heard of. `id` is the
  // store's own key and is not a register field in any module. fieldsNamed
  // rather than fieldOf, so a DUPLICATED api_name still counts as known — it is
  // a different defect, reported separately, not an unknown key.
  for (const key of Object.keys(out)) {
    if (key === 'id') continue
    if (fieldsNamed(spec.module, key).length > 0) continue

    // The pipeline split moved this field to another module. The seed row is
    // not wrong and the register is not missing anything — the RECORD is on the
    // wrong side of the new boundary, because the workbook seeded a Lead at
    // Stage 4 and Stage 4 is an Opportunity now. Reported as its own thing
    // rather than as an unknown key, which it plainly is not.
    const moved = movedRefs.get(`${spec.module}.${key}`)
    if (moved) {
      note({
        collection,
        api_name: key,
        kind: 'moved_module',
        detail: `seed carries "${key}" on a ${collection} record; the split moved that field to "${moved}"`,
      })
      continue
    }

    note({
      collection,
      api_name: key,
      kind: 'unknown_key',
      detail: `seed carries "${key}", which is not a field of module "${spec.module}"`,
    })
  }

  return out
}

function noteUnresolved(collection: string, apiName: string, picklist: string | null, value: unknown) {
  note({
    collection,
    api_name: apiName,
    kind: 'unresolved_value',
    detail: `seed value ${JSON.stringify(value)} is not in picklist "${picklist}" — left as typed`,
  })
}

function toCamelCase(fileName: string): string {
  return fileName.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())
}

// ------------------------------------------------------------ date rebasing

/** yyyy-MM-dd, optionally followed by a time. */
const ISO_DATE = /^(\d{4}-\d{2}-\d{2})([T ].*)?$/
/** yyyy-MM on its own — leads.expected_close_month is written this way. */
const ISO_MONTH = /^(\d{4}-\d{2})$/

export interface SeedAnchor {
  /** The date the workbook's seed sheet was written against. */
  anchor_date: string
}

/**
 * Shifting the seed so the demo opens on a live pipeline.
 *
 * Every date in the workbook is fixed, so a prototype opened three months later
 * shows a registration that expired in April and a gate that closed last
 * quarter. Rather than editing the dates — which the next regenerate would
 * overwrite — the whole seed is translated by `today - anchor_date` as it
 * loads, which preserves every interval the workbook chose exactly.
 *
 * This runs ON SEEDING ONLY: first run, and again on Reset demo data. Rebasing
 * on ordinary load would move every record a day forward each day, and a lead
 * created yesterday would never age.
 */
function shiftDateString(value: string, delta: number): string | null {
  const iso = ISO_DATE.exec(value)
  if (iso) {
    const shifted = format(addDays(parseISO(iso[1]), delta), 'yyyy-MM-dd')
    // Time and zone are carried through untouched. Nothing here parses them, so
    // nothing here can move a timestamp across a DST boundary by accident.
    return `${shifted}${iso[2] ?? ''}`
  }

  const month = ISO_MONTH.exec(value)
  if (month) {
    return format(addDays(parseISO(`${month[1]}-01`), delta), 'yyyy-MM')
  }

  return null
}

/** Deep copy with every ISO date shifted. Non-date strings are left alone. */
function rebase<T>(value: T, delta: number): T {
  if (typeof value === 'string') {
    return (shiftDateString(value, delta) ?? value) as T
  }
  if (Array.isArray(value)) {
    return value.map((v) => rebase(v, delta)) as T
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value)) out[k] = rebase(v, delta)
    return out as T
  }
  return value
}

/** What the last seeding did, surfaced through /api/__seed for the operator. */
export interface SeedStamp {
  anchor_date: string
  seeded_on: string
  delta_days: number
}

/**
 * Every spec/seed/*.json file becomes a collection automatically — add a file
 * there and it is seeded with no code change. Entities that ship no seed data
 * (nothing has been created in them yet) start empty.
 *
 * A file whose name begins with an underscore is configuration for the loader,
 * not data: `_anchor.json` supplies the rebase anchor and never becomes a
 * collection.
 */
export function buildSeedData(now = new Date()): Record<string, unknown> {
  const modules = import.meta.glob('../../../spec/seed/*.json', {
    eager: true,
    import: 'default',
  }) as Record<string, unknown>

  const files = new Map<string, unknown>()
  for (const path in modules) {
    const name = path.match(/([^/]+)\.json$/)?.[1]
    if (name) files.set(name, modules[path])
  }

  const anchor = files.get('_anchor') as SeedAnchor | undefined
  const anchorDate = anchor?.anchor_date
  // One delta for the whole seeding, so two collections can never disagree
  // about what "today" was — including across a run that starts before
  // midnight and finishes after it.
  const delta = anchorDate ? differenceInCalendarDays(now, parseISO(anchorDate)) : 0

  const data: Record<string, unknown> = {}
  for (const [name, rows] of files) {
    if (name.startsWith('_')) continue
    const collection = toCamelCase(name)
    const shifted = delta === 0 ? rows : rebase(rows, delta)
    data[collection] =
      Array.isArray(shifted) && seedNormalisationFor(collection)
        ? (shifted as Item[]).map((row) => normaliseSeedRecord(collection, row))
        : shifted
  }

  // Collections the register describes but the workbook seeds no rows for.
  // They have to exist as empty arrays or the store refuses a create — see
  // useDataStore.create, which only writes into a collection that is an array.
  for (const key of [
    'quotes',
    'deals',
    'gates',
    'transitions',
    'comments',
    // partners CONFLICT ADJUDICATION. The register defines the record; §6.2
    // describes when one arises; the workbook seeds none.
    'conflicts',
    // The 14-stage-review pipeline split. No seed file backs either — every
    // row in both is produced by deriveOpportunitiesFromLeads below, never
    // hand-written into spec/seed.
    'opportunities',
    'conversions',
  ]) {
    if (!(key in data)) data[key] = []
  }

  // Two seeded Leads — LEAD-00119 at Stage 4, LEAD-00122 at Stage 6 — sit on
  // the far side of the pipeline split. Left alone they would be stranded on a
  // Leads screen that stops at Stage 3, and Opportunities would open empty.
  // See lib/spec/pipelineSeed.ts — the SAME function migrates a returning
  // browser's persisted leads, in useDataStore's migrate().
  const derived = deriveOpportunitiesFromLeads(data)

  if (anchorDate) {
    const stamp: SeedStamp = {
      anchor_date: anchorDate,
      seeded_on: format(now, 'yyyy-MM-dd'),
      delta_days: delta,
    }
    derived.__seed = stamp
  }

  scanned = true
  return derived
}

/**
 * What the reconciliation had to do. Empty is the goal: it means the workbook's
 * seed sheet and register sheet finally agree.
 */
export function seedMismatches(): SeedMismatch[] {
  if (!scanned) buildSeedData()
  return mismatches
}
