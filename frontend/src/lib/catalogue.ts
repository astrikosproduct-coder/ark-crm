/**
 * The price book and the catalogue — read-only reference data, bundled with
 * the application.
 *
 * Products, prices, T-shirt sizes, the rate card, support tiers, regions and
 * pricing parameters are the same for every user and change only when the
 * price book is revised. They are not business records, so they have no table
 * and no endpoint: the files in spec/seed are imported at build time and a new
 * revision ships with the next build. Decided 21 Sep 2026, with MSW's removal —
 * no table is created for a module that is not live.
 *
 * Seven files are imported by name rather than globbing spec/seed/*.json: the
 * same folder holds seed Leads and Registrations that the backend's migrate
 * scripts read, and those must not be bundled into the frontend.
 */
import products from '../../spec/seed/products.json'
import prices from '../../spec/seed/prices.json'
import sizes from '../../spec/seed/sizes.json'
import rateCard from '../../spec/seed/rate_card.json'
import supportTiers from '../../spec/seed/support_tiers.json'
import regions from '../../spec/seed/regions.json'
import pricingParams from '../../spec/seed/pricing_params.json'

/** Each catalogue collection, by the collection name a lookup resolves to. */
const CATALOGUE: Record<string, unknown> = {
  products,
  prices,
  sizes,
  rateCard,
  supportTiers,
  regions,
  pricingParams,
}

/** The catalogue's rows for one collection, or undefined if it is not one. */
export function catalogueCollection(collection: string): unknown {
  return CATALOGUE[collection]
}

export function isCatalogueCollection(collection: string): boolean {
  return collection in CATALOGUE
}
