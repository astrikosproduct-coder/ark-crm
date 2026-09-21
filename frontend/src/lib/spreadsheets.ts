import { api } from '@/lib/api'

/**
 * Excel import and export — backend/app/routers/spreadsheets.py (UX roadmap item 4).
 *
 * Through the shared axios client like every other call (CLAUDE.md rule 2).
 * A file is sent as the raw request body: read on the server, checked, and
 * discarded — never stored.
 */

export type SpreadsheetModule = 'leads' | 'opportunities' | 'deals' | 'accounts' | 'contacts' | 'partners'

export const IMPORTABLE: ReadonlySet<SpreadsheetModule> = new Set(['leads', 'accounts', 'contacts', 'partners'])

export interface ImportRowError {
  row: number
  messages: string[]
}

/** A choice the file wrote in its own words — answered once for every row that has it. */
export interface UnknownValue {
  field: string
  label: string
  value: string
  rows: number
  choices: { key: string; label: string }[]
}

/** Names a lookup column gives that aren't in ARK yet, grouped per column. */
export interface MissingRecords {
  field: string
  label: string
  /** "account", "person" */
  noun: string
  names: string[]
  count: number
  rows: number
}

/** {field api_name: {text as written: choice key, or "" to leave it out}} */
export type ValueAnswers = Record<string, Record<string, string>>

export interface ImportReport {
  filename: string
  sheet: string
  header_row: number
  columns: { header: string; field: string | null }[]
  fields: { api_name: string; label: string }[]
  unmapped: string[]
  total: number
  ready: number
  failed: number
  /** Ready rows with a value left out because its column doesn't apply to them. */
  warned: number
  errors: ImportRowError[]
  warnings: ImportRowError[]
  unknown_values: UnknownValue[]
  missing_records: MissingRecords[]
  committed: boolean
  created: string[]
}

export const ACCEPTED_EXTENSIONS = ['.xlsx', '.xls', '.csv']
export const MAX_FILE_BYTES = 5 * 1024 * 1024

function filenameFrom(disposition: string | undefined, fallback: string): string {
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition ?? '')
  if (encoded) return decodeURIComponent(encoded[1])
  const plain = /filename="?([^";]+)"?/i.exec(disposition ?? '')
  return plain ? plain[1] : fallback
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function download(path: string, params: Record<string, string | string[]>, fallback: string): Promise<void> {
  const res = await api.get<Blob>(path, { params, responseType: 'blob' })
  saveBlob(res.data, filenameFrom(res.headers['content-disposition'] as string | undefined, fallback))
}

export function downloadSample(module: SpreadsheetModule, format: 'xlsx' | 'csv'): Promise<void> {
  return download(`/spreadsheets/${module}/template`, { format }, `Astrikos ARK - ${module} import sample.${format}`)
}

/** The export follows the list's own filters, so it holds exactly what the screen shows. */
export function downloadExport(module: SpreadsheetModule, filter: Record<string, string | string[]> = {}): Promise<void> {
  return download(`/spreadsheets/${module}/export`, filter, `Astrikos ARK - ${module}.xlsx`)
}

async function sendFile(path: string, file: File, mapping: Record<string, string>, answers: ValueAnswers): Promise<ImportReport> {
  const params: Record<string, string> = { filename: file.name }
  if (Object.keys(mapping).length) params.mapping = JSON.stringify(mapping)
  if (Object.keys(answers).length) params.answers = JSON.stringify(answers)
  const res = await api.post<ImportReport>(path, file, {
    params,
    headers: { 'Content-Type': 'application/octet-stream' },
    // A thousand rows through the create route takes a while; never cut it short.
    timeout: 0,
  })
  return res.data
}

export function previewImport(module: SpreadsheetModule, file: File, mapping: Record<string, string>, answers: ValueAnswers) {
  return sendFile(`/spreadsheets/${module}/import/preview`, file, mapping, answers)
}

export function commitImport(module: SpreadsheetModule, file: File, mapping: Record<string, string>, answers: ValueAnswers) {
  return sendFile(`/spreadsheets/${module}/import`, file, mapping, answers)
}

/** A blob error body, read back into JSON so ErrorNotice can show the server's words. */
export async function readBlobError(error: unknown): Promise<unknown> {
  const response = (error as { response?: { data?: unknown } })?.response
  if (response?.data instanceof Blob) {
    try {
      response.data = JSON.parse(await response.data.text())
    } catch {
      // not JSON — leave it; ErrorNotice falls back to its generic sentence
    }
  }
  return error
}
