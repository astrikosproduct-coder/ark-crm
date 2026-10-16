import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'

/**
 * Price Books (Products phase 3, 13 Oct 2026) — the books, their editions and
 * the prices in them. Every rule is the server's (backend/app/price_books.py):
 * a regional price is worked out there, and what a save may change is decided
 * there. This file only carries the shapes and the calls.
 */

export const PRICE_BOOKS_MODULE = 'price_books'
export const EDITIONS_MODULE = 'price_book_editions'
export const PRICES_MODULE = 'price_book_entries'
export const SIZES_MODULE = 'deployment_sizes'

export const PRICE_BOOKS = 'price-books'
export const EDITIONS = 'price-book-editions'
export const SIZES = 'sizes'

/** One price. `own` is false for a regional price worked out from the Standard one. */
export interface PriceCell {
  /** A size's id, or null for a product with one price whatever the size. */
  size: string | null
  standard: number | null
  price: number | null
  own: boolean
}

export type PriceShape = 'sized' | 'single' | 'percent'

export interface PriceRow {
  product: string
  item_name: string
  sku_code: string
  catalogue_category: string | null
  pricing_basis: string | null
  unit_of_measure: string | null
  active: boolean
  shape: PriceShape
  cells: PriceCell[]
}

export interface PriceGrid {
  price_book: string
  price_book_name: string
  is_standard: boolean
  currency: string | null
  multiplier: number
  edition: string
  edition_name: string
  edition_status: 'DRAFT' | 'CURRENT' | 'RETIRED'
  /** A draft: any price may be set, changed or taken away. */
  can_change: boolean
  /** The edition in use, Standard book: a product with no price may be given one. */
  can_add: boolean
  sizes: { id: string; size_code: string; active: boolean }[]
  rows: PriceRow[]
}

export interface Edition {
  id: string
  price_book_version: string
  status: 'DRAFT' | 'CURRENT' | 'RETIRED'
  effective_from: string | null
  effective_to: string | null
  notes: string | null
}

export interface PriceBookRow {
  id: string
  price_book_name: string
  is_standard: boolean
  currency: string | null
  active: boolean
}

/** One book's price of every product — in `editionId`, else the edition in use. */
export function usePriceGrid(bookId: string | undefined, editionId: string | undefined) {
  return useQuery({
    queryKey: ['price-grid', bookId, editionId ?? 'current'],
    queryFn: async () =>
      (await api.get<PriceGrid>(`/${PRICE_BOOKS}/${bookId}/prices`, { params: editionId ? { edition: editionId } : {} })).data,
    enabled: Boolean(bookId),
    // A size added, an FX rate changed, an edition made current: each changes
    // this grid from another screen, so it is never served from memory.
    staleTime: 0,
    retry: false,
  })
}

export function useEditions() {
  return useQuery({
    queryKey: ['collection', EDITIONS],
    queryFn: async () => (await api.get<Edition[]>(`/${EDITIONS}`)).data,
    staleTime: 0,
  })
}

export function usePriceBooks() {
  return useQuery({
    queryKey: ['collection', PRICE_BOOKS],
    queryFn: async () => (await api.get<PriceBookRow[]>(`/${PRICE_BOOKS}`)).data,
    staleTime: 30_000,
  })
}

export interface CellChange {
  product: string
  size: string | null
  /** The price, or null to take it away. */
  value: number | null
}

/** Write prices into one book and one edition — all of the cells, or none. */
export function useSavePrices() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ book, ...body }: { book: string; edition: string; cells: CellChange[] }) =>
      (await api.put<PriceGrid>(`/${PRICE_BOOKS}/${book}/prices`, body)).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['price-grid'] })
      // A product's own page shows its Standard price.
      void queryClient.invalidateQueries({ queryKey: ['record', 'products'] })
    },
  })
}

function refreshEditions(queryClient: ReturnType<typeof useQueryClient>) {
  for (const key of [['collection', EDITIONS], ['list', EDITIONS], ['record', EDITIONS], ['price-grid'], ['record', 'products']]) {
    void queryClient.invalidateQueries({ queryKey: key })
  }
}

export function useMakeEditionCurrent(editionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => (await api.post<Edition>(`/${EDITIONS}/${editionId}/make-current`)).data,
    onSuccess: () => refreshEditions(queryClient),
  })
}

export function useDeleteEdition(editionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.delete(`/${EDITIONS}/${editionId}`)
    },
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['record', EDITIONS, editionId] })
      refreshEditions(queryClient)
    },
  })
}
