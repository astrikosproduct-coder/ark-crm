/**
 * The one pricing table still bundled with the application: the pricing
 * parameters — the perpetual multiplier, the onsite premium and their
 * neighbours. They are read-only until CPQ's price rules hold them (phase 4),
 * and shown on CPQ's Price Rules tab.
 *
 * EVERYTHING ELSE THAT WAS HERE IS IN POSTGRESQL NOW, edited in the app:
 *   · products and prices   Products step 1 (12 Oct 2026) and Price Books
 *   · sizes                 CPQ's Sizing Guide — /api/sizes
 *   · regions               the price books themselves — /api/price-books
 *   · the rate card,        Service and Support products, priced in a price
 *     the support tiers     book like everything else
 * (Products phase 3, 13 Oct 2026.) Those files in spec/seed are read once, by
 * the backend's load_price_book.py, and never by the browser.
 *
 * Imported by name rather than globbing spec/seed/*.json: the same folder
 * holds files the backend scripts read, which must not be bundled.
 */
import pricingParams from '../../spec/seed/pricing_params.json'

/** Each bundled collection, by the collection name a lookup resolves to. */
const CATALOGUE: Record<string, unknown> = {
  pricingParams,
}

/** The catalogue's rows for one collection, or undefined if it is not one. */
export function catalogueCollection(collection: string): unknown {
  return CATALOGUE[collection]
}

export function isCatalogueCollection(collection: string): boolean {
  return collection in CATALOGUE
}
