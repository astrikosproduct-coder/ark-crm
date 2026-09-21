import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeftIcon } from 'lucide-react'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { requestDiscard } from '@/store/useUnsavedChangesStore'
import { cn } from '@/lib/utils'

export interface PageTab {
  key: string
  label: string
  /** Drawn before the label — e.g. the Cherry / Trophy on Opportunities' ranked tabs. */
  icon?: ReactNode
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
   * Draw a back control before the title — the reference opens a record screen
   * with one (ARK_brand_UI.md §3.3). List screens are not drilled into and do
   * not get it.
   */
  back?: boolean
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
  back,
  activeTab,
  onTabChange,
}: PageLayoutProps) {
  const navigate = useNavigate()
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
        {back && (
          <button
            type="button"
            aria-label="Back"
            title="Back"
            onClick={() => requestDiscard(() => navigate(-1))}
            className="text-muted-foreground hover:bg-accent hover:text-foreground mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md transition-colors"
          >
            <ArrowLeftIcon className="size-5" />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <h1 className="text-page-title flex flex-wrap items-center gap-2 font-bold">{title}</h1>
          {subtitle && <div className="text-muted-foreground text-label mt-0.5">{subtitle}</div>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>

      <Tabs value={currentTab} onValueChange={changeTab}>
        <TabsList>
          {tabs.map((tab) => (
            <TabsTrigger key={tab.key} value={tab.key}>
              {/* Wrapped, not bare: TabsTrigger is a plain inline element and
                  Tailwind's preflight makes every svg display:block, so an icon
                  dropped straight in stacks ABOVE its label. `flex`, not
                  `inline-flex`: an inline box sits on the text baseline and
                  leaves descender room under it, making icon tabs 2px taller
                  than plain ones and kinking the underline. Drawn only when
                  there is an icon, so plain tabs are untouched. */}
              {tab.icon ? (
                <span className="flex items-center gap-1.5">
                  {tab.icon}
                  {tab.label}
                </span>
              ) : (
                tab.label
              )}
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
