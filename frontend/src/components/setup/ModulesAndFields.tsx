import { useState } from 'react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConversionMappingTab } from '@/components/admin/metadata/ConversionMappingTab'
import { DeletedFieldsTab } from '@/components/admin/metadata/DeletedFieldsTab'
import { FieldsTab } from '@/components/admin/metadata/FieldsTab'
import { LayoutTab } from '@/components/admin/metadata/LayoutTab'
import { ModulesTab } from '@/components/admin/metadata/ModulesTab'
import { requestDiscard } from '@/store/useUnsavedChangesStore'

/**
 * Setup → Customization → Modules and Fields.
 *
 * Step 1 of the Setup rebuild moves Administration's five register tabs in
 * here as they were — each still with its own module picker. Step 2 replaces
 * this with Zoho's arrangement: the module list, and each module opening on
 * Fields · Layout · Unused fields · Conversion Mapping at its own address.
 *
 * Fields and Layout sit side by side for the reason they always did: Fields is
 * the table you read a property off, Layout is the form you see a position in,
 * and the answer to "why is this field there" is on one and the fix on the other.
 */
const TABS = [
  { key: 'modules', label: 'Modules', content: <ModulesTab /> },
  { key: 'fields', label: 'Fields', content: <FieldsTab /> },
  { key: 'layout', label: 'Layout', content: <LayoutTab /> },
  { key: 'conversion', label: 'Conversion mapping', content: <ConversionMappingTab /> },
  { key: 'deleted', label: 'Deleted fields', content: <DeletedFieldsTab /> },
]

export function ModulesAndFields() {
  const [tab, setTab] = useState('modules')

  return (
    // Controlled, and every switch asks the unsaved-changes guard first — as
    // PageLayout does — or Radix would unmount an editor with edits in it.
    <Tabs value={tab} onValueChange={(key) => requestDiscard(() => setTab(key))}>
      <TabsList>
        {TABS.map((t) => (
          <TabsTrigger key={t.key} value={t.key}>
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {TABS.map((t) => (
        <TabsContent key={t.key} value={t.key}>
          {t.content}
        </TabsContent>
      ))}
    </Tabs>
  )
}
