import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'

/**
 * One person's own layout of a list or a board — Zoho's Manage Columns and
 * Kanban View Settings (Release 1.2, 14 Oct 2026).
 *
 * Stored per user in PostgreSQL (/api/view-preferences, table
 * user_view_preferences), so it follows the person to any browser and never
 * reaches anyone else's screen. Nothing is kept in the browser. No settings
 * means the default view — the list_views columns everyone sees today.
 *
 * Field names are register api_names; a caller reads them against the
 * published register and drops one that is no longer there.
 */

export interface ListSettings {
  /** Columns, in order. The list view's first column (the record's name) is always first. */
  columns?: string[]
  /** Column widths in px, by api_name. Absent = the column sizes itself. */
  widths?: Record<string, number>
  page_size?: number
  /** Wrap long text in its cell (the default) or clip it to one line. */
  wrap?: boolean
  /** Columns held at the left while the list scrolls sideways, in order. */
  pinned?: string[]
}

export interface KanbanSettings {
  /** The field whose choices are the columns. Absent = the stage. */
  categorize_by?: string
  /** What a column's total adds up; 'none' shows no total. Absent = value. */
  aggregate_by?: 'none' | 'value' | 'weighted'
  /** The fields a card shows under the name, in order. Absent = the default card. */
  card_fields?: string[]
}

export interface PageSettings {
  /** The view a module's page opens on for this person — 'pipeline', 'top-10'… Absent = its first view. */
  default_view?: string
}

export const PAGE_SIZES = [10, 25, 50, 100] as const

export function useViewPreference<T extends object>(viewKey: string | undefined) {
  const queryClient = useQueryClient()
  const key = ['view-preferences', viewKey]

  const query = useQuery({
    queryKey: key,
    enabled: Boolean(viewKey),
    queryFn: async () => (await api.get<{ settings: T | null }>(`/view-preferences/${viewKey}`)).data.settings,
    staleTime: Infinity,
  })

  // Optimistic: the screen changes as the person clicks, and the server keeps up.
  const save = useMutation({
    mutationFn: async (settings: T) => (await api.put<{ settings: T }>(`/view-preferences/${viewKey}`, { settings })).data.settings,
    onMutate: (settings: T) => queryClient.setQueryData(key, settings),
    onSuccess: (settings) => queryClient.setQueryData(key, settings),
  })
  const reset = useMutation({
    mutationFn: async () => {
      await api.delete(`/view-preferences/${viewKey}`)
    },
    onMutate: () => queryClient.setQueryData(key, null),
  })

  return {
    settings: (query.data ?? null) as T | null,
    /** Has the person's own layout arrived (or is there none to wait for)? */
    ready: !viewKey || query.isFetched,
    save: (settings: T) => save.mutate(settings),
    reset: () => reset.mutate(),
    error: save.error ?? reset.error ?? null,
  }
}
