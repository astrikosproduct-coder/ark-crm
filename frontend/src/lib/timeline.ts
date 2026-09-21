import { companyDayKey } from '@/lib/time'
import { collectionFor, fieldAt, fieldOf, labelForValue } from '@/lib/spec'
import { date as fmtDate, humanize, money, number as fmtNumber, percent } from '@/lib/format'
import type { FieldSpec } from '@/types/field'

/**
 * One record's history, merged from the three trails that record it.
 *
 * THREE TABLES, ONE STORY
 * -----------------------
 * `audit_log`        every create, update and delete, with a before/after diff
 * `stage_transitions` every stage move, with the reason the dialog demanded
 * `conversions`      Lead -> Opportunity -> Deal
 *
 * They are separate tables because they answer to different rules — a stage
 * move needs a reason, an edit does not — but they are one sequence to the
 * person reading them, and splitting that sequence across three screens is how
 * you get a manager who cannot tell whether the value changed before or after
 * the stage moved. Merged here, newest first, grouped by company-calendar day.
 *
 * MERGED IN THE BROWSER, FOR NOW
 * ------------------------------
 * Three requests and a sort, rather than a /timeline endpoint. That is the
 * right first move — it adds no server surface and the three endpoints already
 * existed — and the right second move is a single endpoint, because this one
 * cannot page: it must hold a record's whole history in memory to sort it. The
 * cap on /audit-log is what keeps that bounded until then.
 */

export type TimelineKind = 'created' | 'updated' | 'deleted' | 'pct' | 'stage' | 'conversion'

export interface FieldChange {
  field: string
  /** The register's label for the field, resolved at RENDER time — see below. */
  label: string
  from?: string
  to?: string
  /** A child list was rewritten; there is no before/after to show. */
  list?: boolean
}

export interface TimelineEvent {
  id: string
  kind: TimelineKind
  timestamp: string
  actor: string | null
  /** The one-line headline, for events that are not a field diff. */
  summary?: string
  /** The reason a stage move recorded, when it demanded one. */
  reason?: string | null
  /** A qualifier on the event itself — "skipped ahead", "moved back". */
  note?: string
  changes: FieldChange[]
  /** Rows written before the diff column existed carry no before/after. */
  unknownChanges?: boolean
}

export interface AuditRow {
  id: string
  record_module: string
  record_id: string
  action: string
  actor: string | null
  changed_fields: string[] | null
  changed: { field: string; from?: unknown; to?: unknown; kind?: string }[] | null
  timestamp: string
}

export interface ConversionRow {
  id: string
  source_module: string
  source_id: string
  target_module: string
  target_id: string
  actor: string | null
  timestamp: string
  note: string | null
}

/** How an empty value reads inside the sentence. See displayValue. */
export const BLANK = 'blank value'

/**
 * Record ids a History row can carry outside any register field — a pursuit
 * group's `member` and `primary_pursuit`, a conflict's `primary_registration`.
 * Resolved to the record's name like a lookup, so History never reads
 * "LEAD-00017 → REG-00004".
 */
const COLLECTION_OF_PREFIX: Record<string, string> = {
  LEAD: 'leads',
  OPP: 'opportunities',
  DEAL: 'deals',
  REG: 'registrations',
  CONF: 'conflicts',
  PG: 'pursuit-groups',
}

function collectionOfId(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const match = value.match(/^([A-Z]+)-\d+$/)
  return match ? COLLECTION_OF_PREFIX[match[1]] : undefined
}

/**
 * A stored value, as a person reads it.
 *
 * LABELS ARE RESOLVED HERE, NOT STORED. The audit trail keeps raw values —
 * 'AMBER', 1480000, '2026-12-31' — precisely so that renaming a picklist value
 * in Administration does not rewrite history. The cost is that every render
 * must look the label up, which is this function.
 *
 * `lookups` carries id -> display name for the lookup collections this
 * timeline touches; a lookup whose record could not be resolved falls back to
 * its id, which is at least a reference a person can search for.
 */
export function displayValue(
  field: FieldSpec | undefined,
  raw: unknown,
  lookups: Record<string, string>
): string {
  // "was updated from blank value to Green" reads as a sentence; "from — to
  // Green" does not. The em dash is still right in a dense table of values,
  // which is why it stays the app's mark for absence everywhere else — this
  // is prose, and prose needs a word.
  if (raw === null || raw === undefined || raw === '') return BLANK
  if (typeof raw === 'boolean') return raw ? 'Yes' : 'No'

  if (Array.isArray(raw)) {
    return raw.map((v) => displayValue(field, v, lookups)).join(', ') || '—'
  }

  if (!field) return collectionOfId(raw) ? (lookups[String(raw)] ?? String(raw)) : String(raw)

  switch (field.type) {
    case 'picklist':
    case 'multiselect':
      return labelForValue(field.picklist, raw)
    case 'lookup':
      return lookups[String(raw)] ?? String(raw)
    case 'currency':
      return money(raw)
    case 'percent':
      return percent(raw)
    case 'number':
      return fmtNumber(raw)
    case 'date':
    case 'datetime':
      return fmtDate(raw)
    case 'checkbox':
      return raw ? 'Yes' : 'No'
    case 'computed':
      // A computed field's type is the formula, not the value, so its shape is
      // read off the value: a registration's Exclusivity Expiry Date is a date
      // and should read 12 Dec 2026, not 2026-12-12.
      return typeof raw === 'string' && /^\d{4}-\d{2}-\d{2}/.test(raw) ? fmtDate(raw) : String(raw)
    default:
      return String(raw)
  }
}

/**
 * The register field a diff entry names.
 *
 * A per-stage value is stored as `<api_name>__s<stage>` (see lib/stageScope.ts),
 * so the suffix is stripped before the lookup — otherwise every stage-scoped
 * change in the timeline would render under its raw storage key, which is not
 * a name anybody outside this codebase would recognise.
 */
export function fieldForChange(
  module: string,
  name: string,
  sections?: readonly string[]
): FieldSpec | undefined {
  const base = name.replace(/__s\d+$/, '')
  // `sections` first: where one register sheet describes several records, an
  // api_name can be defined twice — partners.partner is in DEAL REGISTRATION
  // and QUARTERLY SCORECARD — and fieldOf returns nothing for it, so a Partner
  // change rendered as a raw ACC-006. The record's own section says which.
  for (const section of sections ?? []) {
    const hit = fieldAt(module, section, base) ?? fieldAt(module, section, name)
    if (hit) return hit
  }
  return fieldOf(module, base) ?? fieldOf(module, name)
}

/** The stage a per-stage key was captured at, for the label suffix. */
function stageSuffixOf(name: string): string {
  const match = name.match(/__s(\d+)$/)
  return match ? ` (Stage ${match[1]})` : ''
}

/** Every lookup collection the diffs in these rows will need to resolve. */
export function lookupCollectionsOf(
  module: string,
  rows: AuditRow[],
  sections?: readonly string[]
): string[] {
  const collections = new Set<string>()
  for (const row of rows) {
    for (const change of row.changed ?? []) {
      const field = fieldForChange(module, change.field, sections)
      if (field?.type === 'lookup') {
        const collection = collectionFor(field.lookup_target)
        if (collection) collections.add(collection)
        continue
      }
      if (field) continue
      for (const value of [change.from, change.to].flat()) {
        const collection = collectionOfId(value)
        if (collection) collections.add(collection)
      }
    }
  }
  return [...collections]
}

function changesOf(
  module: string,
  row: AuditRow,
  lookups: Record<string, string>,
  sections?: readonly string[]
): FieldChange[] {
  return (row.changed ?? []).map((change) => {
    const field = fieldForChange(module, change.field, sections)
    // Not every changed column is a register field (an older audit row may name
    // one that has no placement, and so no label). Humanised rather than
    // printed raw, so the timeline never shows a storage key.
    const label =
      (field?.label ?? humanize(change.field.replace(/__s\d+$/, ''))) + stageSuffixOf(change.field)
    if (change.kind === 'list') return { field: change.field, label, list: true }
    return {
      field: change.field,
      label,
      from: displayValue(field, change.from, lookups),
      to: displayValue(field, change.to, lookups),
    }
  })
}

/** Headlines for the Progression % / Probability % rows app/progression.py records. */
const PCT_EVENTS: Record<string, string> = {
  stage_pct: 'Progression % and Probability % set from the new stage',
  overridden: 'Progression % / Probability % overridden',
  rung_moved: 'Progression % and Probability % recalculated (retired rule)',
  stage_band: 'Progression % and Probability % reset to the stage band (retired rule)',
}

/** Headlines for the Pursuit Group events app/pursuits.py records. */
const PURSUIT_EVENTS: Record<string, string> = {
  created: 'Pursuit group was created',
  member_added: 'A pursuit joined the pursuit group',
  member_removed: 'A pursuit was removed from the pursuit group',
  primary_changed: 'The primary pursuit was changed',
  primary_registration_changed: "The conflict's primary registration was changed",
  dissolved: 'The pursuit group was dissolved',
}

export interface BuildInput {
  module: string
  /** The record being viewed — decides which END of a conversion this is. */
  recordId: string
  noun: string
  audit: AuditRow[] | undefined
  /** Pipeline records only. A record with no stages passes neither of these. */
  transitions?: { id?: string; from: number; to: number; reason: string | null; is_skip: boolean; is_reversal: boolean; actor: string; timestamp: string }[] | undefined
  conversions?: ConversionRow[] | undefined
  lookups: Record<string, string>
  stageName?: (stage: number) => string
  /** The register sections this record is drawn from — see fieldForChange. */
  sections?: readonly string[]
  /**
   * A headline for an update, when the save means more than its fields — a
   * registration's acknowledgement writes five of them at once, and "5 fields
   * were updated" hides that it was acknowledged.
   */
  summaryOf?: (row: AuditRow) => string | undefined
  /** Headline for every other update — used when merging another record's trail in. */
  updateSummary?: string
}

/**
 * Every recorded event on one record, newest first.
 *
 * An 'updated' row whose diff came back EMPTY is dropped rather than rendered.
 * That is not a lost event: the editor PUTs a whole section, so saving a form
 * without changing anything writes a real audit row with nothing in it, and
 * showing "Priya updated this record" with no change underneath is noise that
 * pushes the real entries off the screen. The row stays in the database, where
 * "was this record opened and saved" is still answerable.
 */
export function buildTimeline({
  module,
  recordId,
  noun,
  audit,
  transitions,
  conversions,
  lookups,
  stageName,
  sections,
  summaryOf,
  updateSummary,
}: BuildInput): TimelineEvent[] {
  const events: TimelineEvent[] = []

  for (const row of audit ?? []) {
    const changes = changesOf(module, row, lookups, sections)

    if (row.action === 'created') {
      events.push({
        id: row.id,
        kind: 'created',
        timestamp: row.timestamp,
        actor: row.actor,
        summary: `${noun[0].toUpperCase()}${noun.slice(1)} was created`,
        changes: [],
      })
      continue
    }

    if (row.action === 'deleted') {
      events.push({
        id: row.id,
        kind: 'deleted',
        timestamp: row.timestamp,
        actor: row.actor,
        summary: `${noun[0].toUpperCase()}${noun.slice(1)} was deleted`,
        changes: [],
      })
      continue
    }

    // A Pursuit Group change (backend/app/pursuits.py::_audit). The server
    // cannot put the event name or the reason in a column of their own, so
    // they ride as `__event` / `__reason` entries in `changed`; lifted out here
    // so the timeline says what happened and why, and lists only real changes.
    if (row.action === 'pursuit') {
      const meta = new Map((row.changed ?? []).filter((c) => c.field.startsWith('__')).map((c) => [c.field, c.to]))
      const real = { ...row, changed: (row.changed ?? []).filter((c) => !c.field.startsWith('__')) }
      const event = String(meta.get('__event') ?? '')
      events.push({
        id: row.id,
        kind: 'updated',
        timestamp: row.timestamp,
        actor: row.actor,
        summary: PURSUIT_EVENTS[event] ?? 'Pursuit group was changed',
        reason: typeof meta.get('__reason') === 'string' ? (meta.get('__reason') as string) : null,
        changes: changesOf(module, real, lookups, sections),
      })
      continue
    }

    // The stage pair (app/progression.py). rung_moved and stage_band are rows
    // the retired evidence ladder wrote before 0022; they stay readable.
    if (row.action in PCT_EVENTS) {
      events.push({
        id: row.id,
        kind: 'pct',
        timestamp: row.timestamp,
        actor: row.actor,
        summary: PCT_EVENTS[row.action],
        changes,
      })
      continue
    }

    // An update with no diff at all is either a save that changed nothing, or
    // a row written before the diff column existed. The two are told apart by
    // whether the column is null (no history was captured) or empty (captured,
    // and nothing moved) — only the first is worth a line on screen.
    if (changes.length === 0) {
      if (row.changed === null) {
        events.push({
          id: row.id,
          kind: 'updated',
          timestamp: row.timestamp,
          actor: row.actor,
          summary: 'Record was updated',
          changes: [],
          unknownChanges: true,
        })
      }
      continue
    }

    events.push({
      id: row.id,
      kind: 'updated',
      timestamp: row.timestamp,
      actor: row.actor,
      summary: summaryOf?.(row) ?? updateSummary,
      changes,
    })
  }

  // A stage move is rendered through the SAME sentence as a field edit —
  // "Stage was updated from X to Y" — rather than a shape of its own. It is a
  // field changing value like any other; the only thing that makes it special
  // is that it carries a reason, which hangs underneath.
  for (const t of transitions ?? []) {
    const marks = [t.is_skip && 'skipped ahead', t.is_reversal && 'moved back'].filter(Boolean)
    events.push({
      id: t.id ?? `${t.timestamp}-${t.from}-${t.to}`,
      kind: 'stage',
      timestamp: t.timestamp,
      actor: t.actor,
      note: marks.length ? (marks.join(', ') as string) : undefined,
      reason: t.reason,
      changes: [
        {
          field: 'stage',
          label: 'Stage',
          from: `${t.from} · ${stageName?.(t.from) ?? ''}`,
          to: `${t.to} · ${stageName?.(t.to) ?? ''}`,
        },
      ],
    })
  }

  // A conversion is ONE event that two records both legitimately show, and it
  // reads differently from each end: the Lead says it became an Opportunity,
  // the Opportunity says where it came from. Which end this is depends on the
  // record being viewed, so the id is compared rather than assumed.
  for (const c of conversions ?? []) {
    const isSource = c.source_id === recordId
    events.push({
      id: c.id,
      kind: 'conversion',
      timestamp: c.timestamp,
      actor: c.actor,
      summary: isSource ? `Converted to ${c.target_id}` : `Converted from ${c.source_id}`,
      reason: c.note,
      changes: [],
    })
  }

  return events.sort((a, b) => b.timestamp.localeCompare(a.timestamp))
}

/** Events grouped under their company-calendar day, newest day first. */
export function groupByDay(events: TimelineEvent[]): { day: string; events: TimelineEvent[] }[] {
  const days: { day: string; events: TimelineEvent[] }[] = []
  for (const event of events) {
    const day = companyDayKey(event.timestamp)
    const last = days[days.length - 1]
    if (last && last.day === day) last.events.push(event)
    else days.push({ day, events: [event] })
  }
  return days
}
