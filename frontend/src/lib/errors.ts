import { fields } from '@/lib/spec'

/**
 * What a person reads when a request fails.
 *
 * The server refuses as `{code, message, details?}` (backend/app/messages.py):
 * one short sentence and, when there is a way forward, a few bullets. This
 * turns ANY axios error into that same shape, so every screen renders a
 * refusal the same way — through <ErrorNotice> — and never has to know
 * whether it came from a rule, a validation error or a dropped connection.
 */
export interface Refusal {
  /** The server's machine code — branch on this, never on the wording. */
  code: string | null
  message: string
  details: string[]
  /** The whole `detail` object, for callers that need its extra keys. */
  raw: Record<string, unknown> | null
}

export interface RefusalOptions {
  /** api_name → form label, for FastAPI validation errors. */
  fieldLabel?: (apiName: string) => string | undefined
  /** Shown when the server gave no sentence of its own. */
  fallback?: string
}

/** A reply with no sentence of its own. Points at the Feedback button so a repeat failure reaches a developer. */
export const GENERIC_FAILURE = "That didn't work. Try again. If it keeps happening, tell us with the Feedback button."

const OFFLINE = "Can't reach ARK right now. Check your connection and try again."

/** Pydantic error types → the words a person understands. Anything unlisted keeps the server's own `msg`. */
const VALIDATION_WORDS: Record<string, string> = {
  missing: 'is required',
  float_parsing: 'enter a number',
  float_type: 'enter a number',
  int_parsing: 'enter a whole number',
  int_type: 'enter a whole number',
  decimal_parsing: 'enter a number',
  decimal_type: 'enter a number',
  date_parsing: 'enter a date',
  date_from_datetime_parsing: 'enter a date',
  date_type: 'enter a date',
  datetime_parsing: 'enter a date and time',
  bool_parsing: 'choose yes or no',
  string_too_long: 'is too long',
  string_type: 'enter text',
  list_type: 'choose from the list',
}

/** Per-stage keys (`on_hold_reason__s3`) label as their base field. */
function labelAnywhere(apiName: string): string {
  const base = apiName.replace(/__s\d+$/, '')
  return fields.find((f) => f.api_name === base)?.label ?? base.replace(/_/g, ' ')
}

function validationLine(item: { loc?: unknown[]; msg?: string; type?: string }, options: RefusalOptions): string {
  const words = (item.type && VALIDATION_WORDS[item.type]) ?? item.msg ?? 'is not valid'
  const last = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : undefined
  // loc ends in "body" when the whole payload is wrong — there is no field to name.
  if (last === undefined || last === null || last === 'body' || typeof last === 'number') return capitalise(words)
  const name = String(last)
  const label = options.fieldLabel?.(name) ?? labelAnywhere(name)
  return `${label}: ${words}`
}

function capitalise(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text
}

export function refusalOf(error: unknown, options: RefusalOptions = {}): Refusal {
  const response = (error as { response?: { data?: { detail?: unknown } } })?.response
  const detail = response?.data?.detail

  if (typeof detail === 'string' && detail) {
    return { code: null, message: detail, details: [], raw: null }
  }

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const raw = detail as Record<string, unknown>
    const message = typeof raw.message === 'string' && raw.message ? raw.message : (options.fallback ?? GENERIC_FAILURE)
    const details = Array.isArray(raw.details) ? raw.details.filter((d): d is string => typeof d === 'string') : []
    return { code: typeof raw.code === 'string' ? raw.code : null, message, details, raw }
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const lines = (detail as { loc?: unknown[]; msg?: string; type?: string }[]).map((item) =>
      validationLine(item, options)
    )
    return lines.length === 1
      ? { code: 'VALIDATION', message: `${lines[0]}.`, details: [], raw: null }
      : { code: 'VALIDATION', message: 'Some values need fixing:', details: lines, raw: null }
  }

  if (response) return { code: null, message: options.fallback ?? GENERIC_FAILURE, details: [], raw: null }
  // An axios error with no response never reached the server. Anything else
  // thrown is a bug in this screen — its own message is for a developer, not
  // for the person using it, so they get the generic sentence.
  const offline = Boolean((error as { isAxiosError?: boolean })?.isAxiosError)
  return { code: null, message: offline ? OFFLINE : (options.fallback ?? GENERIC_FAILURE), details: [], raw: null }
}

/** The refusal's code, or null — for branching without building the whole shape. */
export function refusalCodeOf(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return detail && typeof detail === 'object' && !Array.isArray(detail)
    ? ((detail as { code?: unknown }).code as string | undefined) ?? null
    : null
}
