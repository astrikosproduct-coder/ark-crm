import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { nextId } from '@/lib/idGen'
import { deriveOpportunitiesFromLeads } from '@/lib/spec/pipelineSeed'
import { buildSeedData, normaliseSeedRecord } from '@/lib/spec/seed'

const STORAGE_KEY = 'arkcrm-data'

type Item = Record<string, unknown>

// Collections seeded from spec/seed/*.json start with their given record id
// convention. Anything created fresh in the prototype (leads, deals, quotes,
// gates...) gets an id in the same style — see CLAUDE.md "Conventions".
const ID_PREFIXES: Record<string, { prefix: string; pad: number }> = {
  leads: { prefix: 'LEAD', pad: 5 },
  deals: { prefix: 'DEAL', pad: 5 },
  accounts: { prefix: 'ACC', pad: 3 },
  contacts: { prefix: 'CON', pad: 3 },
  users: { prefix: 'USR', pad: 3 },
  quotes: { prefix: 'QT', pad: 5 },
  gates: { prefix: 'GATE', pad: 4 },
  registrations: { prefix: 'REG', pad: 5 },
  // CLAUDE.md's Conventions list no id shape for a conflict. CONF-0001 follows
  // GATE-0091's four digits; confirm it in the register correction pass.
  conflicts: { prefix: 'CONF', pad: 4 },
  transitions: { prefix: 'TRN', pad: 4 },
  automationLog: { prefix: 'LOG', pad: 5 },
  comments: { prefix: 'CMT', pad: 4 },
  // The 14-stage-review pipeline split. OPP- matches LEAD-/DEAL- at five
  // digits. CONV- has no stated convention either — four digits follows
  // TRN-0001, the other audit-log-shaped record; confirm both in the
  // register correction pass, same as CONF- above.
  opportunities: { prefix: 'OPP', pad: 5 },
  conversions: { prefix: 'CONV', pad: 4 },
}

// Not every seed record uses an "id" field (products key on sku, sizes on
// code, rate_card on level...). Resolve whichever identifying field a record
// actually has instead of forcing the seed data to conform.
function identify(item: unknown): string | undefined {
  if (!item || typeof item !== 'object') return undefined
  const rec = item as Item
  const key = rec.id ?? rec.sku ?? rec.code ?? rec.level ?? rec.tier
  return typeof key === 'string' ? key : undefined
}

function generateId(collection: string, existing: Item[]): string {
  return nextId(ID_PREFIXES[collection] ?? { prefix: collection.toUpperCase(), pad: 5 }, existing)
}

interface DataState {
  data: Record<string, unknown>
  list: (collection: string) => unknown
  getById: (collection: string, id: string) => Item | undefined
  create: (collection: string, item: Item) => Item | undefined
  update: (collection: string, id: string, patch: Item) => Item | undefined
  remove: (collection: string, id: string) => boolean
  reset: () => void
}

export const useDataStore = create<DataState>()(
  persist(
    (set, get) => ({
      data: buildSeedData(),

      list: (collection) => get().data[collection],

      getById: (collection, id) => {
        const items = get().data[collection]
        if (!Array.isArray(items)) return undefined
        return (items as Item[]).find((item) => identify(item) === id)
      },

      create: (collection, item) => {
        const items = get().data[collection]
        if (!Array.isArray(items)) return undefined
        const id = identify(item) ?? generateId(collection, items as Item[])
        const record = { ...item, id }
        set((state) => ({
          data: { ...state.data, [collection]: [...(items as Item[]), record] },
        }))
        return record
      },

      update: (collection, id, patch) => {
        const items = get().data[collection]
        if (!Array.isArray(items)) return undefined
        let updated: Item | undefined
        const next = (items as Item[]).map((item) => {
          if (identify(item) !== id) return item
          updated = { ...item, ...patch }
          return updated
        })
        if (!updated) return undefined
        set((state) => ({ data: { ...state.data, [collection]: next } }))
        return updated
      },

      remove: (collection, id) => {
        const items = get().data[collection]
        if (!Array.isArray(items)) return false
        const next = (items as Item[]).filter((item) => identify(item) !== id)
        if (next.length === (items as Item[]).length) return false
        set((state) => ({ data: { ...state.data, [collection]: next } }))
        return true
      },

      // Reseed from spec/seed rather than reload from an empty store, so a
      // reset takes effect immediately without a page refresh.
      reset: () => {
        localStorage.removeItem(STORAGE_KEY)
        set({ data: buildSeedData() })
      },
    }),
    {
      name: STORAGE_KEY,

      // 1 → 2 introduced seed_normalisation, which renamed accounts.name to
      // accounts.account_name and coerced picklist values to their keys. A
      // browser that already holds the old shape is re-normalised in place
      // rather than being silently left with blank Account Name columns.
      // Records the user typed are already in register api_names, and the
      // normalisation is a no-op on them.
      //
      // 2 → 3 brought registrations under the same rule: the seed writes
      // partner_role "Prime" and registration_status "Active" where the
      // register's keys are PRIME and ACTIVE. Without the bump, a browser that
      // had already persisted the collection would keep the labels and every
      // registration would read as awaiting acknowledgement.
      //
      // 3 → 4 is the 14-stage-review pipeline split. A browser that already
      // holds a Lead at Stage 4-6 predates spec/module_split.json — the same
      // deriveOpportunitiesFromLeads() that populates a fresh seed's
      // Opportunities module runs here on the PERSISTED leads, so an existing
      // browser's own edits are what gets reassigned, not the static seed
      // file. One bump for both new collections (opportunities, conversions)
      // rather than staging two, since they exist for exactly one reason.
      // 4 → 5 normalizes picklists on persisted Opportunities, including rows
      // derived from Leads before the split-aware normalization was added.
      // 5 → 6 remaps the obsolete Deal Stage 7_CLOSE to Project Success.
      version: 6,
      migrate: (persistedState) => {
        const state = persistedState as Partial<DataState> | undefined
        const data = state?.data ?? {}
        const next: Record<string, unknown> = { ...data }
        for (const collection of Object.keys(data)) {
          const rows = data[collection]
          if (!Array.isArray(rows)) continue
          next[collection] = (rows as Item[]).map((row) => {
            const normalized = normaliseSeedRecord(collection, row)
            if (collection === 'deals' && normalized.deal_stage === '7_CLOSE') {
              return { ...normalized, deal_stage: '8_PROJECT_SUCCESS' }
            }
            return normalized
          })
        }
        return { ...state, data: deriveOpportunitiesFromLeads(next) } as DataState
      },

      // Collections already present in localStorage (including ones edited
      // down to []) are kept as-is; only collections never persisted before
      // fall back to the freshly-seeded value. This is what makes seeding
      // "first run only" without a separate seeded flag.
      merge: (persistedState, currentState) => {
        const persisted = (persistedState as Partial<DataState> | undefined)?.data ?? {}
        return {
          ...currentState,
          data: { ...currentState.data, ...persisted },
        }
      },
    }
  )
)
