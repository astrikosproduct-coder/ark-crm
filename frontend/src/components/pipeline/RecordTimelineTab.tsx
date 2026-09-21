import { useCallback, useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import {
  ArrowRightLeftIcon,
  GitBranchIcon,
  PencilIcon,
  PlusCircleIcon,
  TrendingUpIcon,
} from 'lucide-react'

import { api } from '@/lib/api'
import { displayNameOf, idOf } from '@/lib/spec'
import { companyDate, companyTime, COMPANY_TZ_LABEL } from '@/lib/time'
import {
  buildTimeline,
  groupByDay,
  lookupCollectionsOf,
  type AuditRow,
  type BuildInput,
  type ConversionRow,
  type TimelineEvent,
  type TimelineKind,
} from '@/lib/timeline'
import {
  TimelineFilterBar,
  type ActorOption,
  type FieldOption,
} from '@/components/pipeline/TimelineFilterBar'
import { SHOW_OPTIONS, useTimelineFilters } from '@/lib/timelineFilters'
import type { Transition } from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'
import { cn } from '@/lib/utils'

/**
 * One record's whole history, as a timeline.
 *
 * WHAT THIS REPLACED, AND WHY
 * ---------------------------
 * A five-column table of stage transitions — When / From / To / Actor / Reason
 * — and nothing else. A lead edited forty times but never moved stage showed
 * "No transitions recorded yet", which read as "nothing has happened here" when
 * in fact everything had. The audit trail that knew otherwise had existed the
 * whole time and no screen had ever called it.
 *
 * THE FOUR CHOICES IN HERE
 * ------------------------
 * 1. VALUES RENDER AS LABELS, raw values are what is stored. 'AMBER' is shown
 *    as Amber and 1480000 as $1,480,000, resolved against the register at
 *    render time — so renaming a picklist value in Administration changes what
 *    this screen says WITHOUT rewriting what happened. See lib/timeline.ts.
 * 2. EVERY EVENT IS A SENTENCE — "Overall RAG was updated from Amber to Green",
 *    one line per change rather than one per save, with an empty value reading
 *    as "blank value" because "from — to Green" is not a sentence. The em dash
 *    stays the app's mark for absence everywhere that is a table rather than
 *    prose. A stage move uses the SAME sentence, so the timeline has one shape
 *    and not two.
 * 3. A SAVE THAT MOVED MORE THAN THREE FIELDS COLLAPSES to "N fields were
 *    updated", which expands. A pipeline record carries 79 fields and the
 *    editor saves a whole section at a time; without this, one save buries
 *    every stage move above it.
 * 4. CHILD LISTS SAY "updated" and show no diff. Row-level diffing of Demo
 *    Attendees is a much larger job than the scalar diffs and buys much less.
 *
 * WHAT IT CANNOT SHOW
 * -------------------
 * Anything before the diff column shipped. Those audit rows recorded which
 * fields a write carried but never the old values, and no backfill can invent
 * them — so the footer says where history begins rather than letting the
 * absence read as a quiet period.
 */

const ICONS: Record<TimelineKind, typeof PencilIcon> = {
  created: PlusCircleIcon,
  updated: PencilIcon,
  deleted: PencilIcon,
  pct: TrendingUpIcon,
  stage: ArrowRightLeftIcon,
  conversion: GitBranchIcon,
}

/**
 * Another record's audit trail, merged into this one's timeline.
 *
 * A deal registration's conflict adjudication is its own record — its own id,
 * its own audit rows — but it is decided ABOUT the registration, and a reader
 * of the registration's history needs to see it there, in order with the
 * acknowledgement and the supersede it led to.
 */
export interface RelatedTrail {
  /** audit_log.record_module the rows are stored under — `conflicts`. */
  auditModule: string
  recordId: string
  /** The register module its field names resolve against — `partners`. */
  module: string
  sections?: readonly string[]
  /** "conflict adjudication CONF-0001" — headlines every event from this trail. */
  noun: string
}

export interface RecordTimelineTabProps {
  module: string
  recordId: string
  noun: string
  /** Already fetched by the page for the stage rail — reused rather than refetched.
   * Pipeline records only; a record with no stages leaves both out. */
  transitions?: Transition[] | undefined
  stageName?: (stage: number) => string
  /** The register sections this record is drawn from — see fieldForChange. */
  sections?: readonly string[]
  /** Lead -> Opportunity -> Deal. Off for a record that is never converted. */
  showConversions?: boolean
  related?: RelatedTrail[]
  summaryOf?: BuildInput['summaryOf']
}

const capitalise = (s: string) => `${s[0]?.toUpperCase() ?? ''}${s.slice(1)}`

export function RecordTimelineTab({
  module,
  recordId,
  noun,
  transitions,
  stageName,
  sections,
  showConversions = true,
  related,
  summaryOf,
}: RecordTimelineTabProps) {
  const filters = useTimelineFilters()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // The endpoint's own maximum (MAX_LIMIT, backend/app/routers/audit_log.py).
  // Filtering happens here, over the merged timeline, so what is not fetched
  // cannot be filtered — asking for the most the server will give is what keeps
  // the When filter honest, and `truncated` below owns up when even that is not
  // the whole trail.
  const AUDIT_LIMIT = 2000
  const { data: audit, isLoading } = useQuery({
    queryKey: ['audit-log', module, recordId],
    queryFn: async () =>
      (await api.get<AuditRow[]>('/audit-log', { params: { record_id: recordId, _limit: AUDIT_LIMIT } })).data,
    enabled: Boolean(recordId),
  })

  /**
   * Both ends of the conversion trail.
   *
   * /conversions filters on source_id OR target_id, one at a time, and a record
   * can be either: a Lead is the SOURCE of its conversion to an Opportunity,
   * that Opportunity is the TARGET of the same row. Asking only for target_id
   * would leave every converted Lead — the ones whose history most needs the
   * entry, since they go read-only at that moment — with nothing to show.
   */
  const conversionQueries = useQueries({
    queries: (['source_id', 'target_id'] as const).map((key) => ({
      queryKey: ['conversions', key, recordId],
      queryFn: async () =>
        (await api.get<ConversionRow[]>('/conversions', { params: { [key]: recordId } })).data,
      enabled: Boolean(recordId) && showConversions,
    })),
  })

  const relatedQueries = useQueries({
    queries: (related ?? []).map((trail) => ({
      queryKey: ['audit-log', trail.auditModule, trail.recordId],
      queryFn: async () =>
        (
          await api.get<AuditRow[]>('/audit-log', {
            params: { record_module: trail.auditModule, record_id: trail.recordId },
          })
        ).data,
    })),
  })

  const conversions = useMemo(() => {
    const byId = new Map<string, ConversionRow>()
    for (const query of conversionQueries) {
      for (const row of query.data ?? []) byId.set(row.id, row)
    }
    return [...byId.values()]
  }, [conversionQueries])

  const { data: users } = useQuery({
    queryKey: ['collection', 'users'],
    queryFn: async () => (await api.get<Values[]>('/users')).data,
  })

  // Only the lookup collections this record's own diffs actually mention. A
  // timeline with no lookup changes in it fetches nothing extra.
  const collections = useMemo(() => {
    const all = new Set(lookupCollectionsOf(module, audit ?? [], sections))
    ;(related ?? []).forEach((trail, i) => {
      for (const c of lookupCollectionsOf(trail.module, relatedQueries[i]?.data ?? [], trail.sections)) all.add(c)
    })
    return [...all]
  }, [module, audit, sections, related, relatedQueries])

  const lookupQueries = useQueries({
    queries: collections.map((collection) => ({
      queryKey: ['collection', collection],
      queryFn: async () => (await api.get<Values[]>(`/${collection}`)).data,
    })),
  })

  const lookups = useMemo(() => {
    const map: Record<string, string> = {}
    for (const query of lookupQueries) {
      for (const row of query.data ?? []) {
        const id = idOf(row)
        if (id) map[String(id)] = displayNameOf(row)
      }
    }
    return map
  }, [lookupQueries])

  // Memoised because the People filter's option list is derived from it: a
  // fresh function every render would rebuild that list on every keystroke
  // anywhere on the page.
  const nameOf = useCallback(
    (userId: string | null) => {
      if (!userId) return 'ARK'
      const user = users?.find((row) => row.id === userId)
      return user ? displayNameOf(user) : userId
    },
    [users]
  )

  const events = useMemo(() => {
    const own = buildTimeline({
      module,
      recordId,
      noun,
      audit,
      transitions,
      conversions: showConversions ? conversions : undefined,
      lookups,
      stageName,
      sections,
      summaryOf,
    })
    const merged = (related ?? []).flatMap((trail, i) =>
      buildTimeline({
        module: trail.module,
        recordId: trail.recordId,
        noun: trail.noun,
        audit: relatedQueries[i]?.data,
        lookups,
        sections: trail.sections,
        updateSummary: `${capitalise(trail.noun)} was updated`,
      })
    )
    return [...own, ...merged].sort((a, b) => b.timestamp.localeCompare(a.timestamp))
  }, [
    module,
    recordId,
    noun,
    audit,
    transitions,
    conversions,
    showConversions,
    lookups,
    stageName,
    sections,
    summaryOf,
    related,
    relatedQueries,
  ])

  // Only the people who actually touched THIS record. Offering the whole
  // directory would be forty names to find the three that ever appear.
  const actors: ActorOption[] = useMemo(() => {
    const ids = [...new Set(events.map((e) => e.actor).filter(Boolean))] as string[]
    return ids.map((id) => ({ id, name: nameOf(id) })).sort((a, b) => a.name.localeCompare(b.name))
  }, [events, nameOf])

  // Only the fields this record's history has actually changed, by their
  // register LABEL — resolved the same way the sentences below resolve theirs,
  // so renaming a field in Administration renames it here too.
  const fields: FieldOption[] = useMemo(() => {
    const byName = new Map<string, string>()
    for (const event of events) {
      for (const change of event.changes) {
        if (!byName.has(change.field)) byName.set(change.field, change.label)
      }
    }
    return [...byName]
      .map(([apiName, label]) => ({ apiName, label }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [events])

  // On filters.matches, not on `filters` — the hook returns a fresh object each
  // render and the predicate is the only part of it this depends on.
  const matches = filters.matches
  const shown = useMemo(() => events.filter(matches), [events, matches])

  // "Stage changes" only means something on a record that has stages.
  const showOptions = useMemo(
    () => SHOW_OPTIONS.filter((o) => o.key !== 'stages' || stageName),
    [stageName]
  )

  const days = useMemo(() => groupByDay(shown), [shown])

  /** The oldest event of any kind — where this record's recorded history starts. */
  const earliest = events[events.length - 1]?.timestamp

  /** The server gave us everything it will give us, and there was more. */
  const truncated = (audit?.length ?? 0) >= AUDIT_LIMIT

  if (isLoading) return <p className="py-6 text-sm text-muted-foreground">Loading…</p>

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-2 text-sm font-semibold">Timeline History</h2>
        <TimelineFilterBar filters={filters} actors={actors} fields={fields} showOptions={showOptions} />

        <span className="text-muted-foreground ml-auto text-xs">
          {shown.length} event{shown.length === 1 ? '' : 's'} · times in {COMPANY_TZ_LABEL}
        </span>
      </div>

      {days.length === 0 ? (
        /* Two different sentences, deliberately. "Nothing here" about a record
           that has a history is the exact failure this tab was built to end, so
           a filtered empty screen says it is the filter's doing and offers the
           way back. */
        filters.activeCount > 0 ? (
          <div className="space-y-2 py-6">
            <p className="text-sm text-muted-foreground">Nothing matches these filters.</p>
            <button
              type="button"
              className="text-primary text-sm underline underline-offset-2"
              onClick={filters.clearAll}
            >
              Clear filters
            </button>
          </div>
        ) : (
          <p className="py-6 text-sm text-muted-foreground">Nothing recorded yet for this {noun}.</p>
        )
      ) : (
        <div>
          {days.map(({ day, events: dayEvents }, dayIndex) => (
            <section key={day}>
              <DayHeading label={companyDate(day)} first={dayIndex === 0} />
              {dayEvents.map((event, eventIndex) => (
                <TimelineRow
                  key={event.id}
                  event={event}
                  last={dayIndex === days.length - 1 && eventIndex === dayEvents.length - 1}
                  actorName={nameOf(event.actor)}
                  expanded={expanded.has(event.id)}
                  onToggle={() =>
                    setExpanded((prev) => {
                      const next = new Set(prev)
                      if (next.has(event.id)) next.delete(event.id)
                      else next.add(event.id)
                      return next
                    })
                  }
                />
              ))}
            </section>
          ))}
        </div>
      )}

      {earliest && (
        <p className="text-muted-foreground border-t pt-3 text-xs">
          Field-level history starts {companyDate(earliest)}. Changes made before that date were
          not recorded.
          {truncated && ` Only the most recent ${AUDIT_LIMIT} changes are shown, so filters search those.`}
        </p>
      )}
    </div>
  )
}

/**
 * Above this many changes in one save, the row collapses to a count.
 *
 * Three is not arbitrary: a genuine edit — the RAG, the close month and the
 * value — is three fields and reads fine in full. The saves that need
 * collapsing are the whole-section PUTs, which are never this small.
 */
const COLLAPSE_ABOVE = 3

/**
 * THE RAIL'S GEOMETRY, in one place.
 *
 * The line down the timeline is drawn by every row independently, as an
 * absolutely-positioned strip inside a fixed-width column. That only reads as
 * ONE continuous line because the column is the same width in every row — the
 * date heading included, which is why it uses these same constants rather than
 * its own padding. Change the width here and the whole rail stays aligned;
 * change it in one place only and the line develops a kink at every date.
 */
const TIME_COL = 'w-[4.5rem]'
const NODE_COL = 'w-8'

/**
 * A day's heading: the date on a pill, with the rail passing down beside it.
 *
 * The pill sits in the CONTENT column rather than at the far left edge, so the
 * eye follows one vertical line — date, event, event, date — instead of two
 * competing left edges.
 */
function DayHeading({ label, first }: { label: string; first: boolean }) {
  return (
    <div className="flex gap-3">
      <div className={cn(TIME_COL, 'shrink-0')} />
      <div className={cn(NODE_COL, 'relative flex shrink-0 justify-center')}>
        {/* The FIRST heading starts the line at its own middle, so no stub of
            rail hangs above the timeline; later headings are mid-line and let
            it run straight through. */}
        <span
          aria-hidden
          className={cn('bg-border absolute w-px', first ? 'top-1/2 bottom-0' : 'inset-y-0')}
        />
      </div>
      <div className="min-w-0 flex-1 py-2">
        <span className="bg-muted text-foreground rounded-md px-2.5 py-1 text-xs font-medium">
          {label}
        </span>
      </div>
    </div>
  )
}

/**
 * One event: time in the gutter, an icon on the rail, the sentence beside it.
 *
 * ONE SENTENCE PER CHANGE, not one per save. A save that moved three fields
 * draws three lines — "Overall RAG was updated from Amber to Green" — because
 * that is the unit a person actually reads. The save is still the unit of
 * TRUTH: all three carry the same time and the same author, and a save that
 * moved more fields than anyone wants to scan collapses to a count first.
 */
function TimelineRow({
  event,
  actorName,
  expanded,
  onToggle,
  last,
}: {
  event: TimelineEvent
  actorName: string
  expanded: boolean
  onToggle: () => void
  /** The final event on the whole timeline — the rail ends at its node. */
  last: boolean
}) {
  const Icon = ICONS[event.kind]
  const collapsible = event.changes.length > COLLAPSE_ABOVE
  const visible = collapsible && !expanded ? [] : event.changes

  return (
    <div className="flex gap-3">
      <time
        className={cn(
          TIME_COL,
          'text-muted-foreground shrink-0 pt-2.5 text-right text-xs tabular-nums'
        )}
      >
        {companyTime(event.timestamp)}
      </time>

      <div className={cn(NODE_COL, 'relative flex shrink-0 justify-center')}>
        {/* h-[1.625rem] on the last row = mt-1.5 plus half the size-8 node, so
            the line ends exactly at the node's centre instead of trailing off
            below the timeline into nothing. */}
        <span
          aria-hidden
          className={cn('bg-border absolute top-0 w-px', last ? 'h-[1.625rem]' : 'bottom-0')}
        />
        <span className="bg-card border-border relative mt-1.5 flex size-8 items-center justify-center rounded-full border">
          <Icon className="text-muted-foreground size-3.5" />
        </span>
      </div>

      <div className="min-w-0 flex-1 space-y-0.5 pt-2 pb-5">
        {event.summary && <p className="text-sm font-medium">{event.summary}</p>}

        {collapsible && !expanded && (
          <p className="text-sm">
            <span className="font-medium">{event.changes.length} fields</span> were updated{' '}
            <button
              type="button"
              onClick={onToggle}
              className="text-link underline underline-offset-2"
            >
              show
            </button>
          </p>
        )}

        {visible.map((change) => (
          <p key={change.field} className="text-sm">
            <span className="font-medium">{change.label}</span>{' '}
            {change.list ? (
              <span className="text-muted-foreground">was updated</span>
            ) : (
              <>
                <span className="text-muted-foreground">was updated from</span>{' '}
                <span className="font-semibold">{change.from}</span>{' '}
                <span className="text-muted-foreground">to</span>{' '}
                <span className="font-semibold">{change.to}</span>
              </>
            )}
          </p>
        ))}

        {collapsible && expanded && (
          <button
            type="button"
            onClick={onToggle}
            className="text-link text-sm underline underline-offset-2"
          >
            hide
          </button>
        )}

        {event.note && <p className="text-muted-foreground text-sm">{event.note}</p>}

        {event.reason && <p className="text-muted-foreground text-sm">“{event.reason}”</p>}

        {event.unknownChanges && (
          <p className="text-muted-foreground text-xs">
            Recorded before field-level history was captured — the values are not known.
          </p>
        )}

        <p className="text-muted-foreground pt-0.5 text-xs">
          by {actorName} · {companyDate(event.timestamp)}
        </p>
      </div>
    </div>
  )
}
