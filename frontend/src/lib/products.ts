import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { catalogueCollection } from '@/lib/catalogue'
import { fieldsOf, seedNormalisationFor } from '@/lib/spec'

/**
 * Products — the catalogue, read from the server (step 1, 12 Oct 2026) and
 * edited in the app (phase 2, 13 Oct 2026): create, edit, clone, deactivate,
 * delete, import and export. Prices are set in Price Books (lib/priceBooks.ts).
 *
 * Every figure and rule is the server's (backend/app/products.py,
 * backend/app/routers/products.py).
 */

type Row = Record<string, unknown>

export const PRODUCTS_MODULE = 'products'

/** The register field that is a product's key — backend/app/products.py KEY_FIELD. */
const KEY_FIELD = 'product_id'

/**
 * The form sections that are a PRODUCT.
 *
 * The section holding Product ID is the product. Read off the register, so
 * renaming the section in Setup changes nothing here and a field added to it
 * in Setup shows at once. The server asks for the same fields
 * (products.record_fields). Until Products phase 3 the module also described
 * the price matrix and five pricing tables; those are modules of their own now.
 */
export function productSections(): string[] {
  const section = fieldsOf(PRODUCTS_MODULE).find((f) => f.api_name === KEY_FIELD)?.section
  return section ? [section] : []
}

/**
 * A product as its form opens it: every Yes / No box answered.
 *
 * The first load from the price book left Supports Perpetual and its
 * neighbours unanswered, because the file stated none. A form has no third
 * state — an unticked box a person saves IS their "No" — so an unanswered box
 * opens unticked and is saved as shown. `starting` is for a new product: it
 * is on sale unless someone says otherwise.
 */
export function withBoxesAnswered(values: Row, starting = false): Row {
  const out: Row = { ...values }
  const sections = productSections()
  for (const f of fieldsOf(PRODUCTS_MODULE)) {
    if (f.type !== 'checkbox' || !sections.includes(f.section)) continue
    if (out[f.api_name] === null || out[f.api_name] === undefined) out[f.api_name] = false
  }
  if (starting && values.active === undefined) out.active = true
  return out
}

/** Roles that may change the catalogue — backend/app/auth.py CATALOGUE_EDITOR_ROLES. */
const CATALOGUE_EDITOR_ROLES = ['ADMIN', 'DEVELOPER']

/**
 * Whether to DRAW the controls that change the catalogue. Presentation only:
 * the server refuses everyone else whatever the browser shows.
 */
export function useCanEditCatalogue(): boolean {
  const { user } = useAuth()
  return user?.roles.some((role) => CATALOGUE_EDITOR_ROLES.includes(role)) ?? false
}

/**
 * One row of a product's list price: the Standard price book, the edition in
 * use. `size` is the size's name ("XS"), or null for a price that holds at
 * every size. A Support product has a percentage in place of an amount.
 */
export interface ProductPrice {
  product: string
  size: string | null
  list_price_usa_usd: number | null
  pct_of_annual_licence: number | null
  /** The edition's name. */
  price_book_version: string | null
  /** The Standard book's currency — what the amount is in. */
  currency: string | null
}

export type Product = Row & { id: string; prices?: ProductPrice[] }

export function useProduct(id: string | undefined) {
  return useQuery({
    queryKey: ['record', 'products', id],
    queryFn: async () => (await api.get<Product>(`/products/${id}`)).data,
    enabled: Boolean(id),
  })
}

/** What a pursuit adds to its stage's total — backend/app/revenue.py. */
interface Revenue {
  usd: number | null
  counted: boolean
}

export interface ProductPursuit {
  module: 'leads' | 'opportunities' | 'deals'
  id: string
  name: string
  stage: string | null
  status: string | null
  /** The fields that name the product — the Lead's own, or the Deal's Expansion Suites. */
  fields: { module: string; api_name: string }[]
  revenue: Revenue
  /** A Deal whose PO has been received. */
  won: boolean
}

export interface ProductPursuits {
  records: ProductPursuit[]
  /** Each pursuit counted once, however many of its fields name the product. */
  total: { pipeline_usd: number; pipeline_count: number; won_usd: number; won_count: number }
}

export function useProductPursuits(id: string | undefined) {
  return useQuery({
    queryKey: ['product-pursuits', id],
    queryFn: async () => (await api.get<ProductPursuits>(`/products/${id}/pursuits`)).data,
    enabled: Boolean(id),
  })
}

/**
 * The rows of a bundled pricing table, keyed by the register's api_names.
 *
 * Only the pricing parameters are still a file (lib/catalogue.ts), whose keys
 * were written by hand and do not all match the register's. The renames live
 * in spec/extensions.json `seed_normalisation`, not here, so what is drawn is
 * always the register's fields.
 */
export function pricingTable(collection: string): Row[] {
  const raw = catalogueCollection(collection)
  const rows = (Array.isArray(raw) ? raw : raw ? [raw] : []) as Row[]
  const rename = seedNormalisationFor(collection)?.rename ?? {}
  return rows.map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [rename[key] ?? key, value])))
}
