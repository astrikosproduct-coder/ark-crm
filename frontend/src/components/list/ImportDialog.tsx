import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CheckIcon, DownloadIcon, FileSpreadsheetIcon, FileUpIcon, Loader2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Bullets, ErrorNotice, Notice } from '@/components/ui/notice'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  ACCEPTED_EXTENSIONS,
  commitImport,
  downloadSample,
  type ImportReport,
  type ImportRowError,
  MAX_FILE_BYTES,
  previewImport,
  readBlobError,
  type SpreadsheetModule,
  type UnknownValue,
  type ValueAnswers,
} from '@/lib/spreadsheets'
import { cn } from '@/lib/utils'

const IGNORE = '__ignore__'

type Step = 'choose' | 'checking' | 'review' | 'importing' | 'done'

/**
 * Import from a spreadsheet — Zoho's flow (UX roadmap item 4):
 *
 *   1  drop or browse a file; the sample file is one click away
 *   2  every row is checked on the server, nothing saved
 *   3  a column ARK could not place is matched by hand, and a choice written in
 *      the file's own words ("SI") is answered once for every row — then
 *      checked again
 *   4  import — every row, or none
 *
 * The file never leaves this dialog except to be checked; nothing is stored.
 */
export function ImportDialog({
  open,
  onOpenChange,
  module,
  plural,
  noun,
  extraNote,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  module: SpreadsheetModule
  /** "Leads" */
  plural: string
  /** "lead" */
  noun: string
  /** One more bullet under the drop zone — "Leads are imported at Stage 0 · Connect." */
  extraNote?: string
}) {
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<Step>('choose')
  const [file, setFile] = useState<File | null>(null)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  /** The mapping the current report was checked with — Import uses exactly that. */
  const [checkedMapping, setCheckedMapping] = useState<Record<string, string>>({})
  /** What each unrecognised choice means, and the answers the current report was checked with. */
  const [answers, setAnswers] = useState<ValueAnswers>({})
  const [checkedAnswers, setCheckedAnswers] = useState<ValueAnswers>({})
  /** Every unrecognised choice this file has shown, so an answered one can still be changed. */
  const [asked, setAsked] = useState<UnknownValue[]>([])
  const [error, setError] = useState<unknown>(null)
  const [dragging, setDragging] = useState(false)

  const reset = () => {
    setStep('choose')
    setFile(null)
    setReport(null)
    setMapping({})
    setCheckedMapping({})
    setAnswers({})
    setCheckedAnswers({})
    setAsked([])
    setError(null)
  }

  const close = (next: boolean) => {
    if (step === 'checking' || step === 'importing') return
    if (!next) reset()
    onOpenChange(next)
  }

  const check = async (chosen: File, withMapping: Record<string, string>, withAnswers: ValueAnswers) => {
    setError(null)
    const extension = chosen.name.slice(chosen.name.lastIndexOf('.')).toLowerCase()
    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
      setError(localError('Use an XLSX, XLS or CSV file.'))
      return
    }
    if (chosen.size > MAX_FILE_BYTES) {
      setError(localError('The file is larger than 5 MB. Split it into smaller files.'))
      return
    }
    setFile(chosen)
    setStep('checking')
    try {
      const next = await previewImport(module, chosen, withMapping, withAnswers)
      setReport(next)
      setCheckedMapping(withMapping)
      setCheckedAnswers(withAnswers)
      setAsked((before) => [
        ...before,
        ...next.unknown_values.filter((u) => !before.some((b) => b.field === u.field && b.value === u.value)),
      ])
      setStep('review')
    } catch (err) {
      setError(err)
      setStep(report ? 'review' : 'choose')
    }
  }

  const runImport = async () => {
    if (!file) return
    setError(null)
    setStep('importing')
    try {
      setReport(await commitImport(module, file, checkedMapping, checkedAnswers))
      setStep('done')
      // Every list, board and lookup that could show the new records.
      await queryClient.invalidateQueries()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: { report?: ImportReport } } } })?.response?.data?.detail
      if (detail?.report) setReport(detail.report)
      setError(err)
      setStep('review')
    }
  }

  const sample = async (format: 'xlsx' | 'csv') => {
    setError(null)
    try {
      await downloadSample(module, format)
    } catch (err) {
      setError(await readBlobError(err))
    }
  }

  // A column matched or a choice answered since the last check has not been checked yet.
  const unmappedChanged =
    JSON.stringify(mapping) !== JSON.stringify(checkedMapping) || JSON.stringify(answers) !== JSON.stringify(checkedAnswers)

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[88vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import {plural}</DialogTitle>
          <DialogDescription>
            {step === 'done' ? 'Import finished.' : 'Every row is checked before anything is saved.'}
          </DialogDescription>
        </DialogHeader>

        {(step === 'choose' || step === 'checking') && (
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              const dropped = e.dataTransfer.files?.[0]
              if (dropped && step === 'choose') void check(dropped, {}, {})
            }}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center text-sm',
              dragging ? 'border-primary bg-primary/5' : 'border-border'
            )}
          >
            {step === 'checking' ? (
              <>
                <Loader2Icon className="text-primary size-8 animate-spin" />
                <p className="font-medium">Checking {file?.name}…</p>
                <p className="text-muted-foreground">A large file can take up to a minute.</p>
              </>
            ) : (
              <>
                <FileUpIcon className="text-primary size-9" />
                <p className="font-medium">Drag and drop the file here</p>
                <p className="text-muted-foreground">- or -</p>
                <Button type="button" variant="outline" size="sm" onClick={() => input.current?.click()}>
                  Browse Files
                </Button>
                <input
                  ref={input}
                  id={`import-file-${module}`}
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  className="hidden"
                  onChange={(e) => {
                    const chosen = e.target.files?.[0]
                    e.target.value = ''
                    if (chosen) void check(chosen, {}, {})
                  }}
                />
                <p className="text-muted-foreground">Supported file formats are XLSX, CSV and XLS</p>
                <p className="text-muted-foreground flex items-center gap-1.5">
                  <DownloadIcon className="size-3.5" />
                  Download sample file:
                  <button type="button" className="text-link hover:underline" onClick={() => void sample('csv')}>
                    CSV
                  </button>
                  or
                  <button type="button" className="text-link hover:underline" onClick={() => void sample('xlsx')}>
                    XLSX
                  </button>
                </p>
              </>
            )}
          </div>
        )}

        {step === 'choose' && (
          <Bullets
            className="text-muted-foreground text-sm"
            items={[
              'Start from the sample file. It has dropdowns and says what each column takes.',
              'Accounts and people named in the file must already be in ARK. Import Accounts first.',
              'Up to 1,000 rows and 5 MB per file.',
              extraNote,
            ]}
          />
        )}

        {(step === 'review' || step === 'importing') && report && (
          <div className="space-y-3 text-sm">
            <div className="flex items-center gap-2">
              <FileSpreadsheetIcon className="text-muted-foreground size-4" />
              <span className="font-medium">{report.filename}</span>
              <span className="text-muted-foreground">· sheet “{report.sheet}”</span>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <Stat label="Rows" value={report.total} />
              <Stat label="Ready" value={report.ready} tone="good" />
              <Stat label="Need fixing" value={report.failed} tone={report.failed ? 'bad' : undefined} />
            </div>

            {report.unmapped.length > 0 && (
              <div className="space-y-1.5 rounded-md border px-3 py-2">
                <p className="font-medium">Columns ARK didn’t recognise</p>
                <p className="text-muted-foreground text-xs">Match each to a field, or leave it out.</p>
                {report.unmapped.map((header) => (
                  <div key={header} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
                    <span className="truncate" title={header}>
                      {header}
                    </span>
                    <Select
                      value={mapping[header] === undefined ? IGNORE : mapping[header] || IGNORE}
                      onValueChange={(value) => setMapping((m) => ({ ...m, [header]: value === IGNORE ? '' : value }))}
                    >
                      <SelectTrigger className="h-8 w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={IGNORE}>Leave it out</SelectItem>
                        {report.fields
                          .filter((f) => !report.columns.some((c) => c.field === f.api_name))
                          .map((f) => (
                            <SelectItem key={f.api_name} value={f.api_name}>
                              {f.label}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            )}

            {asked.length > 0 && (
              <div className="space-y-1.5 rounded-md border px-3 py-2">
                <p className="font-medium">Choices ARK didn’t recognise</p>
                <p className="text-muted-foreground text-xs">Pick what each one means. It applies to every row that uses it.</p>
                {asked.map((u) => {
                  const answer = answers[u.field]?.[u.value]
                  return (
                    <div key={`${u.field}|${u.value}`} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
                      <span className="truncate" title={`${u.value} · ${u.label}`}>
                        “{u.value}”
                        <span className="text-muted-foreground">
                          {' '}
                          · {u.label} · {u.rows} {u.rows === 1 ? 'row' : 'rows'}
                        </span>
                      </span>
                      <Select
                        value={answer === undefined ? '' : answer || IGNORE}
                        onValueChange={(value) =>
                          setAnswers((a) => ({ ...a, [u.field]: { ...a[u.field], [u.value]: value === IGNORE ? '' : value } }))
                        }
                      >
                        <SelectTrigger className="h-8 w-full">
                          <SelectValue placeholder="Choose what it means" />
                        </SelectTrigger>
                        <SelectContent>
                          {u.choices.map((c) => (
                            <SelectItem key={c.key} value={c.key}>
                              {c.label}
                            </SelectItem>
                          ))}
                          <SelectItem value={IGNORE}>Leave it blank</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )
                })}
              </div>
            )}

            {unmappedChanged && (
              <Button type="button" size="sm" variant="outline" disabled={step === 'importing'} onClick={() => file && void check(file, mapping, answers)}>
                Check again with these answers
              </Button>
            )}

            {report.missing_records.length > 0 && (
              <Notice
                tone="warning"
                boxed
                lead="Some names in the file aren’t in ARK yet."
                bullets={[
                  ...report.missing_records.map(
                    (m) =>
                      `${m.label}: ${m.count} ${nounFor(m.noun, m.count)} in ${m.rows} ${m.rows === 1 ? 'row' : 'rows'} · ${m.names.join(', ')}${m.count > m.names.length ? ', …' : ''}`
                  ),
                  'Add them in ARK or import them first, then check this file again.',
                ]}
              />
            )}

            {report.failed > 0 ? (
              <>
                <Notice
                  tone="warning"
                  boxed
                  lead={`${report.failed} ${report.failed === 1 ? 'row needs' : 'rows need'} fixing before anything can be imported.`}
                  bullets={['Fix them in the file, save it, and choose it again.']}
                />
                <RowTable rows={report.errors} heading="What to fix" className="max-h-64" />
                {report.failed > report.errors.length && (
                  <p className="text-muted-foreground text-xs">
                    Showing the first {report.errors.length} rows that need fixing.
                  </p>
                )}
              </>
            ) : (
              <Notice
                tone="info"
                boxed
                lead={`All ${report.ready} ${report.ready === 1 ? noun : plural.toLowerCase()} are ready to import.`}
                bullets={['Each is created as if saved from its form, and shows in its History.']}
              />
            )}

            {report.warned > 0 && (
              <>
                <Notice
                  tone="info"
                  boxed
                  lead={`${report.warned} ${report.warned === 1 ? 'row has a value' : 'rows have values'} that will be left out.`}
                  bullets={['Those columns don’t apply to those rows. The rows still import.']}
                />
                <RowTable rows={report.warnings} heading="Left out" className="max-h-40" />
              </>
            )}
          </div>
        )}

        {step === 'done' && report && (
          <Notice
            lead={
              <span className="flex items-center gap-2 font-medium">
                <CheckIcon className="size-4 text-emerald-600 dark:text-emerald-400" />
                {report.created.length} {report.created.length === 1 ? noun : plural.toLowerCase()} imported
              </span>
            }
            bullets={['They are in the list now.']}
          />
        )}

        {error ? <ErrorNotice error={error} /> : null}

        <DialogFooter>
          {step === 'done' ? (
            <Button type="button" onClick={() => close(false)}>
              Close
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={() => close(false)} disabled={step === 'checking' || step === 'importing'}>
                Cancel
              </Button>
              {(step === 'review' || step === 'importing') && (
                <>
                  <Button type="button" variant="outline" onClick={reset} disabled={step === 'importing'}>
                    Choose another file
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void runImport()}
                    disabled={step === 'importing' || !report || report.failed > 0 || report.ready === 0 || unmappedChanged}
                    title={unmappedChanged ? 'Check again with the matched columns first.' : undefined}
                  >
                    {step === 'importing' ? 'Importing…' : `Import ${report?.ready ?? 0} ${report?.ready === 1 ? noun : plural.toLowerCase()}`}
                  </Button>
                </>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RowTable({ rows, heading, className }: { rows: ImportRowError[]; heading: string; className?: string }) {
  return (
    <div className={cn('overflow-y-auto rounded-md border', className)}>
      <table className="w-full text-left text-sm">
        <thead className="bg-muted/50 text-muted-foreground sticky top-0 text-xs">
          <tr>
            <th className="w-16 px-3 py-1.5 font-medium">Row</th>
            <th className="px-3 py-1.5 font-medium">{heading}</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((e) => (
            <tr key={e.row} className="align-top">
              <td className="px-3 py-1.5 tabular-nums">{e.row}</td>
              <td className="px-3 py-1.5">
                <Bullets items={e.messages} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function nounFor(noun: string, count: number) {
  if (count === 1) return noun
  return noun === 'person' ? 'people' : `${noun}s`
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'good' | 'bad' }) {
  return (
    <div className="rounded-md border px-3 py-1.5">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p
        className={cn(
          'text-lg font-semibold tabular-nums',
          tone === 'good' && value > 0 && 'text-emerald-700 dark:text-emerald-400',
          tone === 'bad' && 'text-amber-700 dark:text-amber-400'
        )}
      >
        {value.toLocaleString()}
      </p>
    </div>
  )
}

/** A refusal made before the file leaves the browser, in the server's own shape. */
function localError(message: string) {
  return { response: { data: { detail: { code: 'FILE_REFUSED', message } } } }
}
