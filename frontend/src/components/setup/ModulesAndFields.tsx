import type { ReactNode } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { ArrowLeftIcon } from 'lucide-react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConversionMappingTab } from '@/components/admin/metadata/ConversionMappingTab'
import { FieldsTab } from '@/components/admin/metadata/FieldsTab'
import { LayoutTab } from '@/components/admin/metadata/LayoutTab'
import { ModulesTab } from '@/components/admin/metadata/ModulesTab'
import { UnusedFieldsTab } from '@/components/admin/metadata/UnusedFieldsTab'
import { ErrorBox, LoadingRow } from '@/components/admin/metadata/shared'
import { useMetadataModules } from '@/lib/metadata'
import { PIPELINE_MODULES } from '@/lib/spec'
import type { SetupAddress } from './setupMap'

/**
 * Setup → Customization → Modules and Fields, as Zoho has it.
 *
 *   /setup/customization/modules                        the module list
 *   /setup/customization/modules/deals/fields           one module, one tab
 *
 * A module opens on Fields · Layout · Unused fields, plus Conversion Mapping
 * on a pipeline module (Leads, Opportunities, Deals). Each tab is an address,
 * so a link or a reload lands where it was — and a tab change is a navigation,
 * which the app-wide unsaved-changes guard already holds for an editor with
 * edits in it.
 *
 * Fields and Layout sit side by side for the reason they always did: Fields is
 * the table you read a property off, Layout is the form you see a position in,
 * and the answer to "why is this field there" is on one and the fix on the other.
 */
export function ModulesAndFields({ at }: { at: SetupAddress }) {
  const [moduleKey, tab] = at.rest

  if (!moduleKey) {
    return (
      <>
        <h1 className="text-page-title mb-4 font-bold">Modules and Fields</h1>
        <ModulesTab moduleHref={(key) => `${at.path}/${key}/fields`} />
      </>
    )
  }
  // Keyed by module: opening another one starts its screens fresh, rather than
  // carrying a search or an open dialog across from the last.
  return (
    <ModuleView
      key={moduleKey}
      base={at.path}
      moduleKey={moduleKey}
      tab={tab}
      extra={at.rest.length > 2}
    />
  )
}

const TABS: {
  slug: string
  label: string
  pipelineOnly?: boolean
  render: (moduleKey: string) => ReactNode
}[] = [
  { slug: 'fields', label: 'Fields', render: (m) => <FieldsTab moduleKey={m} /> },
  { slug: 'layout', label: 'Layout', render: (m) => <LayoutTab moduleKey={m} /> },
  { slug: 'unused-fields', label: 'Unused fields', render: (m) => <UnusedFieldsTab moduleKey={m} /> },
  {
    slug: 'conversion-mapping',
    label: 'Conversion Mapping',
    pipelineOnly: true,
    render: (m) => <ConversionMappingTab moduleKey={m} />,
  },
]

function ModuleView({
  base,
  moduleKey,
  tab,
  extra,
}: {
  base: string
  moduleKey: string
  tab: string | undefined
  extra: boolean
}) {
  const navigate = useNavigate()
  const { data: modules = [], isLoading, isError, error } = useMetadataModules()

  if (isLoading) return <LoadingRow what="the module" />
  if (isError) return <ErrorBox error={error} />

  // A module the register does not have goes back to the list; a tab this
  // module does not have, or anything past the tab, goes to its Fields.
  const module = modules.find((m) => m.module_key === moduleKey)
  if (!module) return <Navigate to={base} replace />
  const tabs = TABS.filter((t) => !t.pipelineOnly || PIPELINE_MODULES.includes(moduleKey))
  if (extra || !tabs.some((t) => t.slug === tab)) {
    return <Navigate to={`${base}/${moduleKey}/fields`} replace />
  }

  return (
    <>
      <div className="mb-4 flex items-center gap-2">
        <Link
          to={base}
          aria-label="Back to Modules and Fields"
          title="Modules and Fields"
          className="text-muted-foreground hover:bg-accent hover:text-foreground flex size-8 shrink-0 items-center justify-center rounded-md transition-colors"
        >
          <ArrowLeftIcon className="size-5" />
        </Link>
        <h1 className="text-page-title font-bold">{module.label}</h1>
        {!module.active && <span className="text-muted-foreground text-sm">Inactive</span>}
      </div>

      <Tabs value={tab} onValueChange={(slug) => navigate(`${base}/${moduleKey}/${slug}`)}>
        <TabsList>
          {tabs.map((t) => (
            <TabsTrigger key={t.slug} value={t.slug}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.slug} value={t.slug}>
            {t.slug === tab && t.render(moduleKey)}
          </TabsContent>
        ))}
      </Tabs>
    </>
  )
}
