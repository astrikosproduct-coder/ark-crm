import { QueryClient } from '@tanstack/react-query'

/**
 * Defaults chosen for screens people type into.
 *
 * refetchOnWindowFocus is OFF deliberately. A record editor is keyed on the
 * query's dataUpdatedAt so it re-hydrates when the record changes underneath
 * it; with focus refetching on, alt-tabbing away and back re-fetched the
 * record, changed that timestamp, remounted the editor and threw away whatever
 * was half-typed in it. Nothing is auto-saved behind the user any more, so that
 * silent loss is not acceptable — a record is refetched when something actually
 * invalidates it instead.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
})
