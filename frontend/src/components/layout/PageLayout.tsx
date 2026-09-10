import { useState, type ReactNode } from 'react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { requestDiscard } from '@/store/useUnsavedChangesStore'
import { cn } from '@/lib/utils'

export interface PageTab {
  key: string
  label: string
  content: ReactNode
}

interface PageLayoutProps {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  tabs: PageTab[]
  /** List screens need the room; record screens read better narrow. */
  wide?: boolean
  /**
   * Controlled tab selection. Optional — a page that does not care leaves both
   * out and the tabs manage themselves. A page whose header actions depend on
   * which tab is open passes them, so it can stop offering an Edit button that
   * edits something the reader is not looking at.
   */
  activeTab?: string
  onTabChange?: (key: string) => void
}

export function PageLayout({
  title,
  subtitle,
  actions,
  tabs,
  wide,
  activeTab,
  onTabChange,
}: PageLayoutProps) {
  /**
   * Tabs are always controlled here, even when the caller does not care which
   * one is open. Radix would otherwise switch on its own and unmount whatever
   * editor was in the old tab — with unsaved edits in it — before anything had
   * a chance to ask.
   */
  const [internalTab, setInternalTab] = useState(() => tabs[0]?.key)
  const currentTab = activeTab ?? internalTab

  const changeTab = (key: string) =>
    requestDiscard(() => {
      setInternalTab(key)
      onTabChange?.(key)
    })

  return (
    <div className={cn('mx-auto px-6 py-6', wide ? 'max-w-7xl' : 'max-w-5xl')}>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-page-title flex flex-wrap items-center gap-2 font-bold">{title}</h1>
          {subtitle && <div className="text-muted-foreground text-label mt-0.5">{subtitle}</div>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>

      <Tabs value={currentTab} onValueChange={changeTab}>
        <TabsList>
          {tabs.map((tab) => (
            <TabsTrigger key={tab.key} value={tab.key}>
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((tab) => (
          <TabsContent key={tab.key} value={tab.key}>
            {tab.content}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
