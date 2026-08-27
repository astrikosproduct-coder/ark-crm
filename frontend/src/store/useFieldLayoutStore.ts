import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const STORAGE_KEY = 'arkcrm-field-layout'

function sectionKey(module: string, section: string): string {
  return `${module}::${section}`
}

interface FieldLayoutState {
  /** section key -> api_names in the order this browser dragged them to.
   * Never the field register's own order — that stays in spec/fields.json,
   * untouched. This is a per-browser display preference layered on top, the
   * same way a draft is a preference layered on top of the last save. */
  order: Record<string, string[]>
  /** Persists the section's full field order after a drag completes. */
  setOrder: (module: string, section: string, apiNames: string[]) => void
  /** CLAUDE.md rule: "Reset demo data" must not leave a stale field order
   * pointing at fields a reset section no longer carries. */
  clearAll: () => void
}

export const useFieldLayoutStore = create<FieldLayoutState>()(
  persist(
    (set) => ({
      order: {},

      setOrder: (module, section, apiNames) => {
        const key = sectionKey(module, section)
        set((state) => ({ order: { ...state.order, [key]: apiNames } }))
      },

      clearAll: () => {
        localStorage.removeItem(STORAGE_KEY)
        set({ order: {} })
      },
    }),
    { name: STORAGE_KEY }
  )
)

/** Reactive read of one section's stored order, or undefined if never dragged. */
export function useFieldOrder(module: string, section: string): string[] | undefined {
  return useFieldLayoutStore((s) => s.order[sectionKey(module, section)])
}

/**
 * Applies a stored order on top of the section's natural (spec `order`) field
 * list. A field the stored order does not name — new to the register, or
 * newly visible under a condition — keeps its natural relative position,
 * appended after the fields that ARE named. Nothing here can move a field
 * out of `fields`: the return value is always a permutation of it, never a
 * superset, so a section's own fields can never leave the section.
 */
export function applyFieldOrder<T extends { api_name: string }>(fields: T[], order: string[] | undefined): T[] {
  if (!order || order.length === 0) return fields
  const remaining = new Map(fields.map((f) => [f.api_name, f]))
  const ordered: T[] = []
  for (const name of order) {
    const f = remaining.get(name)
    if (!f) continue
    ordered.push(f)
    remaining.delete(name)
  }
  for (const f of fields) {
    if (remaining.has(f.api_name)) ordered.push(f)
  }
  return ordered
}
