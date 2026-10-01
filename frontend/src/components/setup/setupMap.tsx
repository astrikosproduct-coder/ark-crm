import type { ReactNode } from 'react'
import {
  CodeXmlIcon,
  DatabaseIcon,
  Settings2Icon,
  SlidersHorizontalIcon,
  UsersIcon,
  type LucideIcon,
} from 'lucide-react'

import { ApiNamesTab } from '@/components/admin/metadata/ApiNamesTab'
import { PublishTab } from '@/components/admin/metadata/PublishTab'
import { StagesTab } from '@/components/admin/metadata/StagesTab'
import { ModulesAndFields, ModulesAndFieldsMenu } from './ModulesAndFields'
import { insideModule } from './modulesPaths'
import { RolesPanel, UsersPanel } from './UsersRoles'

/**
 * The map of Setup — Zoho's Setup, repositioned for ARK.
 *
 * ONE LIST, FOUR READERS: the home page's cards, the left menu on every item
 * page, the search box on both, and SetupPage's lookup of the address all read
 * this. An item added here is findable, linked and routed at once; none of them
 * can disagree about what exists.
 *
 * Every item has its own address — /setup/<category>/<item>. An item with no
 * `render` is scheduled, not missing: it opens on "Coming in a later phase",
 * because nothing in ARK is hidden (decided 24 Sep 2026). An item marked
 * `nested` owns the addresses below its own as well —
 * /setup/customization/modules/deals/fields — and is handed the rest.
 */
export interface SetupItem {
  slug: string
  label: string
  /** Words someone might search for that are not in the label. */
  keywords?: string
  /** The screen. Absent: "Coming in a later phase". */
  render?: (at: SetupAddress) => ReactNode
  /** Accepts addresses below its own, handed over as `at.rest`. */
  nested?: boolean
  /** Draws its own page heading, because it changes with `at.rest`. */
  ownHeading?: boolean
  /**
   * Its own left panel at this address, in place of Setup's category menu —
   * Zoho's "‹ Modules" inside a module (4b). Undefined or null: the menu.
   */
  menu?: (at: SetupAddress) => ReactNode | null
}

/** Where a Setup item was opened: its own address, and what follows it. */
export interface SetupAddress {
  path: string
  rest: string[]
}

export interface SetupCategory {
  slug: string
  label: string
  icon: LucideIcon
  items: SetupItem[]
}

export const SETUP: SetupCategory[] = [
  {
    slug: 'general',
    label: 'General',
    icon: Settings2Icon,
    items: [
      { slug: 'company-details', label: 'Company Details', keywords: 'name address time zone organisation' },
      { slug: 'fiscal-year', label: 'Fiscal Year', keywords: 'financial year april start month' },
      { slug: 'currencies', label: 'Currencies', keywords: 'currency exchange rate fx usd money' },
    ],
  },
  {
    slug: 'users-and-control',
    label: 'Users and Control',
    icon: UsersIcon,
    items: [
      { slug: 'users', label: 'Users', keywords: 'people employees add user deactivate', render: () => <UsersPanel /> },
      { slug: 'roles', label: 'Roles', keywords: 'developer admin access', render: () => <RolesPanel /> },
      { slug: 'profiles-and-sharing', label: 'Profiles and Sharing', keywords: 'permissions security access control' },
    ],
  },
  {
    slug: 'customization',
    label: 'Customization',
    icon: SlidersHorizontalIcon,
    items: [
      {
        slug: 'modules',
        label: 'Modules and Fields',
        keywords: 'field layout sections deleted unused conversion mapping form global sets picklist dropdown choices',
        nested: true,
        ownHeading: true,
        render: (at) => <ModulesAndFields at={at} />,
        menu: (at) => (insideModule(at.rest) ? <ModulesAndFieldsMenu at={at} /> : null),
      },
      {
        slug: 'pipelines-and-stages',
        label: 'Pipelines and Stages',
        keywords: 'stage progression probability pipeline',
        render: () => <StagesTab />,
      },
    ],
  },
  {
    slug: 'data-administration',
    label: 'Data Administration',
    icon: DatabaseIcon,
    items: [
      { slug: 'import-export', label: 'Import and Export', keywords: 'excel csv spreadsheet upload download' },
      { slug: 'audit-log', label: 'Audit Log', keywords: 'history who changed' },
      { slug: 'recycle-bin', label: 'Recycle Bin', keywords: 'deleted restore trash' },
    ],
  },
  {
    slug: 'developer-space',
    label: 'Developer Space',
    icon: CodeXmlIcon,
    items: [
      {
        // The only screen that shows an api_name, a module key or a choice's
        // stored value — Zoho keeps them in its developer area too (4a).
        slug: 'api-names',
        label: 'API Names',
        keywords: 'api name key identifier stored value developer column',
        render: () => <ApiNamesTab />,
      },
      {
        slug: 'versions',
        label: 'Versions',
        keywords: 'publish rollback roll back history draft',
        render: () => <PublishTab />,
      },
      { slug: 'register-health', label: 'Register Health', keywords: 'validate errors warnings spec' },
      { slug: 'feedback', label: 'Feedback', keywords: 'messages reviewers queue' },
    ],
  },
]

export function setupPath(category: SetupCategory, item: SetupItem): string {
  return `/setup/${category.slug}/${item.slug}`
}

/**
 * The item at `<category>/<item>[/…]` — the part of the address after /setup/.
 * Anything below the item's own address is refused unless the item is `nested`.
 */
export function findSetupItem(
  address: string
): { category: SetupCategory; item: SetupItem; at: SetupAddress } | undefined {
  const [categorySlug, itemSlug, ...rest] = address.split('/').filter(Boolean)
  const category = SETUP.find((c) => c.slug === categorySlug)
  const item = category?.items.find((i) => i.slug === itemSlug)
  if (!category || !item) return undefined
  if (rest.length > 0 && !item.nested) return undefined
  return { category, item, at: { path: setupPath(category, item), rest } }
}

/**
 * Does the search text find this item? Every word typed must appear in the
 * item's label, its category's label or its keywords — so "deleted fields" and
 * "currency" both land somewhere, and a stray letter does not match everything.
 */
export function matchesSetup(category: SetupCategory, item: SetupItem, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return true
  const haystack = `${item.label} ${category.label} ${item.keywords ?? ''}`.toLowerCase()
  return words.every((word) => haystack.includes(word))
}
