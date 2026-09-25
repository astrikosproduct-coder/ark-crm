import type { ReactNode } from 'react'
import {
  CodeXmlIcon,
  DatabaseIcon,
  Settings2Icon,
  SlidersHorizontalIcon,
  UsersIcon,
  type LucideIcon,
} from 'lucide-react'

import { PicklistsTab } from '@/components/admin/metadata/PicklistsTab'
import { PublishTab } from '@/components/admin/metadata/PublishTab'
import { StagesTab } from '@/components/admin/metadata/StagesTab'
import { ModulesAndFields } from './ModulesAndFields'
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
 * because nothing in ARK is hidden (decided 24 Sep 2026).
 */
export interface SetupItem {
  slug: string
  label: string
  /** Words someone might search for that are not in the label. */
  keywords?: string
  /** The screen. Absent: "Coming in a later phase". */
  render?: () => ReactNode
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
        keywords: 'field layout sections deleted unused conversion mapping form',
        render: () => <ModulesAndFields />,
      },
      {
        slug: 'pipelines-and-stages',
        label: 'Pipelines and Stages',
        keywords: 'stage progression probability pipeline',
        render: () => <StagesTab />,
      },
      {
        slug: 'picklists',
        label: 'Picklists',
        keywords: 'dropdown values choices global sets',
        render: () => <PicklistsTab />,
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

/** The item at `<category>/<item>` — the part of the address after /setup/. */
export function findSetupItem(
  rest: string
): { category: SetupCategory; item: SetupItem } | undefined {
  const [categorySlug, itemSlug, ...extra] = rest.split('/').filter(Boolean)
  if (extra.length > 0) return undefined
  const category = SETUP.find((c) => c.slug === categorySlug)
  const item = category?.items.find((i) => i.slug === itemSlug)
  return category && item ? { category, item } : undefined
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
