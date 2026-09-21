import { FilterIcon, XIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  datesNeeded,
  SHOW_OPTIONS,
  type TimelineFilters,
  WHEN_OPTIONS,
  type WhenKey,
} from '@/lib/timelineFilters'

export interface ActorOption {
  id: string
  name: string
}

export interface FieldOption {
  apiName: string
  label: string
}

/**
 * The History tab's filter control: one button, one panel.
 *
 * WHY A PANEL AND NOT THE OLD CHIP ROW
 * ------------------------------------
 * The tab used to carry four always-visible chips for the event kind and a
 * bare actor dropdown beside them. That was fine at two filters and stopped
 * being fine at four: Show, People, When and Field laid out in a row push the
 * event count off the line and leave the timeline itself starting a screen
 * further down. One Filter button, the same one the lists use
 * (components/list/ListFilterBar.tsx), keeps the header to a single line and
 * gives the app one filter affordance instead of two dialects.
 *
 * WHAT IS STILL VISIBLE WITH THE PANEL SHUT
 * -----------------------------------------
 * Every filter that is on, as a removable chip. A filtered screen that looks
 * unfiltered is how someone concludes a field was never touched, and this tab
 * exists because a screen once said "No transitions recorded yet" about a
 * record that had been edited forty times.
 *
 * FIELD IS NOT IN THE REFERENCE, AND IS THE POINT
 * -----------------------------------------------
 * Zoho's timeline filter offers Modules / Users / Sources / time. Modules means
 * nothing here — this is one record — and Sources is renamed Show, because what
 * varies is the kind of event, not where it came from. Field is added: "what
 * has ever happened to Estimated Value" is the question an audit trail is
 * actually opened for, and the diff column has stored the answer all along.
 */
export function TimelineFilterBar({
  filters,
  actors,
  fields,
  showOptions = SHOW_OPTIONS,
}: {
  filters: TimelineFilters
  /** The people who appear in THIS record's history — never the whole directory. */
  actors: ActorOption[]
  /** The fields this record's history has actually changed. */
  fields: FieldOption[]
  /** Trimmed by the caller — a record with no stages is not offered "Stage changes". */
  showOptions?: typeof SHOW_OPTIONS
}) {
  const needed = datesNeeded(filters.when)
  const showLabel = showOptions.find((o) => o.key === filters.show)?.label
  const whenLabel = WHEN_OPTIONS.find((o) => o.key === filters.when)?.label
  const whoLabel = actors.find((a) => a.id === filters.who)?.name
  const fieldLabel = fields.find((f) => f.apiName === filters.field)?.label

  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-8 gap-1.5">
            <FilterIcon className="size-3.5" />
            Filter
            {filters.activeCount > 0 && (
              <span className="bg-primary text-primary-foreground rounded-full px-1.5 text-[11px] leading-4">
                {filters.activeCount}
              </span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80 space-y-3 p-3">
          <Row label="Show">
            <Select value={filters.show} onValueChange={filters.setShow}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {showOptions.map((option) => (
                  <SelectItem key={option.key} value={option.key}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>

          {actors.length > 1 && (
            <Row label="People">
              <Select value={filters.who} onValueChange={filters.setWho}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Everyone</SelectItem>
                  {actors.map((actor) => (
                    <SelectItem key={actor.id} value={actor.id}>
                      {actor.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Row>
          )}

          <Row label="When">
            <Select value={filters.when} onValueChange={(v) => filters.setWhen(v as WhenKey)}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WHEN_OPTIONS.map((option) => (
                  <SelectItem key={option.key} value={option.key}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>

          {/* The date boxes appear under the choice that needs them rather than
              behind a submenu: one date is one box, a range is two, and both
              are visible while being typed. */}
          {needed > 0 && (
            <Row label={needed === 2 ? 'From' : 'On'}>
              <div className="flex items-center gap-1.5">
                <Input
                  type="date"
                  className="h-8 text-xs"
                  value={filters.from}
                  onChange={(e) => filters.setFrom(e.target.value)}
                  aria-label={needed === 2 ? 'From date' : 'Date'}
                />
                {needed === 2 && (
                  <>
                    <span className="text-muted-foreground text-xs">to</span>
                    <Input
                      type="date"
                      className="h-8 text-xs"
                      value={filters.to}
                      onChange={(e) => filters.setTo(e.target.value)}
                      aria-label="To date"
                    />
                  </>
                )}
              </div>
            </Row>
          )}

          {fields.length > 1 && (
            <Row label="Field">
              <Select value={filters.field || 'all'} onValueChange={filters.setField}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="Any field" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any field</SelectItem>
                  {fields.map((f) => (
                    <SelectItem key={f.apiName} value={f.apiName}>
                      {f.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Row>
          )}

          {filters.activeCount > 0 && (
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-2"
              onClick={filters.clearAll}
            >
              Clear filters
            </button>
          )}
        </PopoverContent>
      </Popover>

      {filters.show !== 'all' && <Chip label={showLabel ?? ''} onRemove={() => filters.setShow('all')} />}
      {filters.who !== 'all' && <Chip label={whoLabel ?? filters.who} onRemove={() => filters.setWho('all')} />}
      {filters.when !== 'any' && (
        <Chip
          label={
            filters.when === 'range' && filters.from && filters.to
              ? `${filters.from} to ${filters.to}`
              : filters.when === 'on' && filters.from
                ? filters.from
                : (whenLabel ?? '')
          }
          onRemove={() => filters.setWhen('any')}
        />
      )}
      {filters.field && <Chip label={fieldLabel ?? filters.field} onRemove={() => filters.setField('all')} />}
    </>
  )
}

/** A label in a fixed column so the four controls line up down their left edge. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground w-12 shrink-0 text-xs">{label}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="border-primary/40 bg-primary/5 text-foreground inline-flex h-7 max-w-64 items-center gap-1 rounded-full border pr-1 pl-2.5 text-xs">
      <span className="truncate">{label}</span>
      <button type="button" aria-label={`Remove the ${label} filter`} className="hover:bg-accent rounded-full p-0.5" onClick={onRemove}>
        <XIcon className="size-3" />
      </button>
    </span>
  )
}
