import { PIPELINE_MODULES } from '@/lib/spec'

/**
 * The addresses under Setup → Customization → Modules and Fields, in one
 * place for the page, its left panel and the Setup map (Setup rebuild, 4b):
 *
 *   …/modules                               Modules · Global Sets — the list
 *   …/modules/global-sets                   the shared lists
 *   …/modules/leads/layout                  a module's layouts
 *   …/modules/leads/layout/12               the layout editor
 *   …/modules/leads/fields                  Field Listing
 *   …/modules/leads/map-dependency          Map Dependency Fields
 *   …/modules/leads/conversion-mapping      Leads and Opportunities only
 *
 * `global-sets` cannot collide with a module: a module key has no hyphen.
 */
export const GLOBAL_SETS = 'global-sets'

export type ModuleTab = 'layout' | 'fields' | 'map-dependency' | 'conversion-mapping'

export const MODULE_TAB_LABEL: Record<ModuleTab, string> = {
  layout: 'Layout',
  fields: 'Fields',
  'map-dependency': 'Map Dependency Fields',
  'conversion-mapping': 'Conversion Mapping',
}

/**
 * A conversion leaves every pipeline module but the last — a Lead becomes an
 * Opportunity (or a paid pilot's Deal), an Opportunity a Deal. Read from the
 * pipeline's own order, never listed here.
 */
export function convertsFrom(moduleKey: string): boolean {
  return PIPELINE_MODULES.slice(0, -1).includes(moduleKey)
}

/** The module's tabs, in Zoho's order. */
export function tabsFor(moduleKey: string): ModuleTab[] {
  const tabs: ModuleTab[] = ['layout', 'fields', 'map-dependency']
  if (convertsFrom(moduleKey)) tabs.push('conversion-mapping')
  return tabs
}

/** Where a module opens: on `keep` when it has that tab, else on Layout. */
export function moduleHref(base: string, moduleKey: string, keep?: string): string {
  const tab = tabsFor(moduleKey).find((t) => t === keep) ?? 'layout'
  return `${base}/${moduleKey}/${tab}`
}

/** Inside a module — where the left panel is the module list, not Setup's menu. */
export function insideModule(rest: string[]): boolean {
  return Boolean(rest[0]) && rest[0] !== GLOBAL_SETS
}
