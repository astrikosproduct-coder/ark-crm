import type { ReferrerSpec } from '@/components/record/DeleteRecordDialog'

/**
 * Where a record can be pointed at from.
 *
 * Only the COLLECTIONS are listed. Which fields inside them point at what is
 * read out of spec/fields.json at scan time, so a new lookup added to the
 * register is picked up without editing this file — see
 * DeleteRecordDialog's pointingFields().
 *
 * `module` differs from `collection` for registrations, whose fields the
 * register files under `partners`.
 */

/** Collections that can name an Account. */
export const ACCOUNT_REFERRERS: ReferrerSpec[] = [
  { collection: 'leads', module: 'leads', basePath: '/leads' },
  { collection: 'opportunities', module: 'opportunities', basePath: '/opportunities' },
  { collection: 'deals', module: 'deals', basePath: '/deals' },
  { collection: 'contacts', module: 'contacts', basePath: '/contacts' },
  { collection: 'registrations', module: 'registrations', basePath: '/partners/registrations' },
  { collection: 'quotes', module: 'quotes' },
]

/**
 * Collections that can name a Contact.
 *
 * Accounts is absent on purpose: the account/contact link lives on the CONTACT
 * (contacts.account), so an account never points back at a person and deleting
 * a contact cannot orphan one.
 */
export const CONTACT_REFERRERS: ReferrerSpec[] = [
  { collection: 'leads', module: 'leads', basePath: '/leads' },
  { collection: 'opportunities', module: 'opportunities', basePath: '/opportunities' },
  { collection: 'deals', module: 'deals', basePath: '/deals' },
  { collection: 'quotes', module: 'quotes' },
]
