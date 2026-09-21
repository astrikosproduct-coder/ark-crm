import { useState } from 'react'
import { ChevronDownIcon, DownloadIcon, Loader2Icon, PlusIcon, UploadIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ImportDialog } from '@/components/list/ImportDialog'
import { ErrorNotice } from '@/components/ui/notice'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { downloadExport, IMPORTABLE, readBlobError, type SpreadsheetModule } from '@/lib/spreadsheets'
import { cn } from '@/lib/utils'

/**
 * A list screen's header action — Zoho's split button (reference shared 17 Sep
 * 2026): "Create Lead" on the left, ▾ on the right opening Import and Export.
 *
 * A module with nothing to create by hand (Deals are born by conversion) gets
 * the ▾ half alone, labelled by what it holds. Import is offered only where the
 * server accepts one — Opportunities and Deals are export-only.
 */
export function ModuleActions({
  module,
  plural,
  noun,
  createLabel,
  onCreate,
  exportFilter,
  importNote,
}: {
  module: SpreadsheetModule
  plural: string
  noun: string
  createLabel?: string
  onCreate?: () => void
  /** The list's current filters, so an export holds what the screen shows. */
  exportFilter?: () => Record<string, string | string[]>
  importNote?: string
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const canImport = IMPORTABLE.has(module)
  const split = Boolean(onCreate && createLabel)

  const runExport = async () => {
    setMenuOpen(false)
    setError(null)
    setExporting(true)
    try {
      await downloadExport(module, exportFilter?.() ?? {})
    } catch (err) {
      setError(await readBlobError(err))
    } finally {
      setExporting(false)
    }
  }

  const item = 'hover:bg-accent flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm'

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-stretch">
        {split && (
          <Button type="button" onClick={onCreate} className="rounded-r-none">
            <PlusIcon className="size-4" />
            {createLabel}
          </Button>
        )}
        <Popover open={menuOpen} onOpenChange={setMenuOpen}>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant={split ? 'default' : 'outline'}
              aria-label={`More ${plural.toLowerCase()} actions`}
              className={cn(split && 'border-primary-foreground/25 rounded-l-none border-l px-2.5')}
              disabled={exporting}
            >
              {exporting ? <Loader2Icon className="size-4 animate-spin" /> : !split && <span>Actions</span>}
              <ChevronDownIcon className="size-4" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-52 p-1">
            {canImport && (
              <button
                type="button"
                className={item}
                onClick={() => {
                  setMenuOpen(false)
                  setImporting(true)
                }}
              >
                <UploadIcon className="text-muted-foreground size-4" />
                Import {plural}
              </button>
            )}
            <button type="button" className={item} onClick={() => void runExport()}>
              <DownloadIcon className="text-muted-foreground size-4" />
              Export {plural}
            </button>
          </PopoverContent>
        </Popover>
      </div>
      {error ? <ErrorNotice error={error} className="max-w-xs text-right" /> : null}
      {canImport && (
        <ImportDialog open={importing} onOpenChange={setImporting} module={module} plural={plural} noun={noun} extraNote={importNote} />
      )}
    </div>
  )
}
