import { Navigate, useNavigate } from 'react-router-dom'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ComingSoon } from '@/pages/ComingSoon'
import { ConversionMappingTab } from '@/components/admin/metadata/ConversionMappingTab'
import { FieldsTab } from '@/components/admin/metadata/FieldsTab'
import { GlobalSetsTab } from '@/components/admin/metadata/GlobalSetsTab'
import { LayoutEditor } from '@/components/admin/metadata/LayoutEditor'
import { LayoutsList } from '@/components/admin/metadata/LayoutsList'
import { ModulesTab } from '@/components/admin/metadata/ModulesTab'
import { ErrorBox, LoadingRow } from '@/components/admin/metadata/shared'
import { useMetadataLayouts, useMetadataModules } from '@/lib/metadata'
import { ModulesNavigator } from './ModulesNavigator'
import {
  GLOBAL_SETS,
  MODULE_TAB_LABEL,
  moduleHref,
  tabsFor,
  type ModuleTab,
} from './modulesPaths'
import type { SetupAddress } from './setupMap'

/**
 * Setup → Customization → Modules and Fields, as Zoho has it (Setup rebuild,
 * 4b, 1 Oct 2026; the addresses are listed in modulesPaths.ts).
 *
 * The list page is Zoho's Modules · Global Sets pair. A module opens on its
 * Layout tab — Zoho's list of layouts, the name opening the editor — then
 * Fields (Zoho's Field Listing), Map Dependency Fields, and Conversion Mapping
 * on the modules a conversion leaves from. Inside a module the left panel is
 * the module list (ModulesNavigator), not Setup's menu: see setupMap's `menu`.
 *
 * Every tab is an address, so a link or a reload lands where it was, and a tab
 * change is a navigation the app-wide unsaved-changes guard can hold.
 */
export function ModulesAndFields({ at }: { at: SetupAddress }) {
  const [moduleKey, tab, layoutId, ...extra] = at.rest

  if (!moduleKey || moduleKey === GLOBAL_SETS) {
    if (at.rest.length > 1) return <Navigate to={at.path} replace />
    return (
      <ListPage
        base={at.path}
        showing={moduleKey ? 'sets' : 'modules'}
        moduleHref={(key) => moduleHref(at.path, key)}
      />
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
      layoutId={layoutId}
      extra={extra.length > 0}
    />
  )
}

/** The left panel while a module is open — Zoho's "‹ Modules". */
export function ModulesAndFieldsMenu({ at }: { at: SetupAddress }) {
  const [moduleKey, tab] = at.rest
  return (
    <ModulesNavigator
      base={at.path}
      current={moduleKey}
      hrefFor={(key) => moduleHref(at.path, key, tab)}
    />
  )
}

/** Modules and Fields' own page: Zoho's Modules · Global Sets pair. */
function ListPage({
  base,
  showing,
  moduleHref,
}: {
  base: string
  showing: 'modules' | 'sets'
  moduleHref: (key: string) => string
}) {
  const navigate = useNavigate()
  return (
    <>
      <h1 className="text-page-title mb-4 font-bold">Modules and Fields</h1>
      <Tabs
        value={showing}
        onValueChange={(next) => navigate(next === 'sets' ? `${base}/${GLOBAL_SETS}` : base)}
      >
        <TabsList>
          <TabsTrigger value="modules">Modules</TabsTrigger>
          <TabsTrigger value="sets">Global Sets</TabsTrigger>
        </TabsList>
        <TabsContent value="modules">
          {showing === 'modules' && <ModulesTab moduleHref={moduleHref} />}
        </TabsContent>
        <TabsContent value="sets">
          {showing === 'sets' && <GlobalSetsTab moduleHref={moduleHref} />}
        </TabsContent>
      </Tabs>
    </>
  )
}

function ModuleView({
  base,
  moduleKey,
  tab,
  layoutId,
  extra,
}: {
  base: string
  moduleKey: string
  tab: string | undefined
  layoutId: string | undefined
  extra: boolean
}) {
  const navigate = useNavigate()
  const { data: modules = [], isLoading, isError, error } = useMetadataModules()

  if (isLoading) return <LoadingRow what="the module" />
  if (isError) return <ErrorBox error={error} />

  // A module the register does not have goes back to the list. A tab this
  // module does not have — including the old Unused fields, which is on the
  // layout now — or anything past it, goes to its Layout.
  const module = modules.find((m) => m.module_key === moduleKey)
  if (!module) return <Navigate to={base} replace />
  const tabs = tabsFor(moduleKey)
  const known = tabs.find((t) => t === tab)
  const editorAddress = known === 'layout' && layoutId !== undefined
  if (!known || extra || (layoutId !== undefined && !editorAddress)) {
    return <Navigate to={`${base}/${moduleKey}/layout`} replace />
  }

  if (editorAddress) {
    return (
      <LayoutEditorPage
        listHref={`${base}/${moduleKey}/layout`}
        moduleKey={moduleKey}
        moduleLabel={module.label}
        layoutId={Number(layoutId)}
      />
    )
  }

  const render = (t: ModuleTab) => {
    switch (t) {
      case 'layout':
        return (
          <LayoutsList
            moduleKey={moduleKey}
            layoutHref={(id) => `${base}/${moduleKey}/layout/${id}`}
          />
        )
      case 'fields':
        return <FieldsTab moduleKey={moduleKey} />
      case 'map-dependency':
        return <ComingSoon label="Map Dependency Fields" />
      case 'conversion-mapping':
        return <ConversionMappingTab moduleKey={moduleKey} />
    }
  }

  return (
    <>
      <div className="mb-4 flex items-center gap-2">
        <h1 className="text-page-title font-bold">{module.label}</h1>
        {!module.active && <span className="text-muted-foreground text-sm">Off</span>}
      </div>

      <Tabs value={known} onValueChange={(slug) => navigate(`${base}/${moduleKey}/${slug}`)}>
        <TabsList>
          {tabs.map((t) => (
            <TabsTrigger key={t} value={t}>
              {MODULE_TAB_LABEL[t]}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t} value={t}>
            {t === known && render(t)}
          </TabsContent>
        ))}
      </Tabs>
    </>
  )
}

/**
 * The layout editor's page — Zoho's full-screen editor (4c). The app shell
 * drops the sidebar and top bar at this address (modulesPaths.isLayoutEditorPath),
 * so the editor's own header is the top of the screen.
 */
function LayoutEditorPage({
  listHref,
  moduleKey,
  moduleLabel,
  layoutId,
}: {
  listHref: string
  moduleKey: string
  moduleLabel: string
  layoutId: number
}) {
  const { data: layouts = [], isLoading } = useMetadataLayouts(moduleKey)
  if (isLoading) return <LoadingRow what="the layout" />
  const layout = layouts.find((l) => l.id === layoutId)
  if (!layout) return <Navigate to={listHref} replace />
  return (
    <LayoutEditor moduleKey={moduleKey} moduleLabel={moduleLabel} layout={layout} listHref={listHref} />
  )
}
