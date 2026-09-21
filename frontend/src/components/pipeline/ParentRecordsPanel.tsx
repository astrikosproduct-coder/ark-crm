import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDownIcon, ChevronRightIcon } from 'lucide-react'

import { RecordForm } from '@/components/form/RecordForm'
import type { PipelineRecordContext } from '@/components/pipeline/types'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useResolvedRecord } from '@/hooks/useResolvedRecord'
import { api } from '@/lib/api'
import { stageFieldOf, stageLabel, stageNumberOf } from '@/lib/pipeline'
import { displayNameOf, sectionsFor } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

function idOf(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

/**
 * One parent record, fetched under the same query key useResolvedRecord uses,
 * so a page that has already resolved its chain pays nothing for this.
 */
export function useParentRecord(module: string, id: string | undefined) {
  return useQuery({
    queryKey: ['record', module, id],
    queryFn: async () => (await api.get<Values>(`/${module}/${id}`)).data,
    enabled: Boolean(id),
  })
}

/**
 * The ids of the records this one came from, nearest first.
 *
 * A Deal names its Opportunity AND its Lead. A Deal made straight from a Lead
 * — a paid POC / pilot — names only the Lead, and has no Opportunity to show.
 * An Opportunity names its Lead. When a Deal's own parent_lead is blank the
 * Opportunity's is used, because it is the same pursuit.
 */
export function useLineage(ctx: PipelineRecordContext) {
  const module = ctx.spec.module
  const opportunityId = module === 'deals' ? idOf(ctx.values?.parent_opportunity) : undefined
  const opportunity = useParentRecord('opportunities', opportunityId)
  const leadId =
    module === 'leads'
      ? undefined
      : (idOf(ctx.values?.parent_lead) ?? idOf(opportunity.data?.parent_lead))
  const lead = useParentRecord('leads', leadId)
  return { module, opportunityId, opportunity, leadId, lead }
}

/**
 * The Related tab's "Read through" sections: what the records this one came
 * from recorded in their OWN stages, read-only.
 *
 * Decided 16 Sep 2026: identity is shown here and only here. The Details tab
 * used to carry a READ THROUGH THE PARENT section of 25 identity fields, all of
 * them the Lead's, and nothing at all of the Opportunity's own work — the RFP,
 * the revenue and cost lines, the evaluations, the payment schedule. Each
 * parent is now drawn from its own record, so every identity field appears
 * under the Lead that owns it, and a Deal finally shows its Opportunity.
 *
 * The same on Opportunities and Deals. A Lead has no parents and draws nothing.
 *
 * COLLAPSED UNTIL ASKED FOR (18 Sep 2026)
 * ---------------------------------------
 * Each parent draws as one line — its name and the stage it stopped at — and
 * opens on click. A Deal used to open this tab with two full read-only forms
 * stacked above its own related lists, which is a lot of screen for records
 * whose work is finished; the lists people came here for started below the
 * fold. Nothing was removed to fix that, because nothing here is a duplicate:
 * a parent's STAGE sections are shown here and nowhere else, while the identity
 * fields on the Details tab are read through the parent rather than copied from
 * it. The two answer different questions, so both stay and one of them waits
 * to be asked.
 */
export function ParentRecordsPanel({ ctx }: { ctx: PipelineRecordContext }) {
  const { module, opportunityId, opportunity, leadId, lead } = useLineage(ctx)
  // An Opportunity stores no name of its own; it is its Lead's, read through.
  const opportunityName = displayNameOf(useResolvedRecord('opportunities', opportunity.data).values)
  const leadName = lead.data ? displayNameOf(lead.data) : ''

  if (module === 'leads' || !ctx.values) return null

  return (
    <div className="space-y-4">
      {module === 'deals' &&
        (opportunityId ? (
          <ParentSection
            title="Read through Parent Opportunity"
            module="opportunities"
            basePath="/opportunities"
            noun="opportunity"
            id={opportunityId}
            name={opportunityName}
            record={opportunity.data}
            isLoading={opportunity.isLoading}
            isError={opportunity.isError}
          />
        ) : (
          <section className="space-y-1">
            <h3 className="text-sm font-semibold">Read through Parent Opportunity</h3>
            <p className="text-muted-foreground text-sm">
              {leadId
                ? `This Deal was made directly from ${leadName || 'its Lead'} — a paid POC / pilot — so there is no Opportunity stage to show.`
                : 'This Deal names no parent Opportunity.'}
            </p>
          </section>
        ))}

      {leadId ? (
        <ParentSection
          title="Read through Parent Lead"
          module="leads"
          basePath="/leads"
          noun="lead"
          id={leadId}
          name={leadName}
          record={lead.data}
          isLoading={lead.isLoading}
          isError={lead.isError}
        />
      ) : (
        <section className="space-y-1">
          <h3 className="text-sm font-semibold">Read through Parent Lead</h3>
          <p className="text-muted-foreground text-sm">No parent Lead is linked to this record.</p>
        </section>
      )}
    </div>
  )
}

function ParentSection({
  title,
  module,
  basePath,
  noun,
  id,
  name,
  record,
  isLoading,
  isError,
}: {
  title: string
  module: string
  basePath: string
  noun: string
  id: string
  /** The parent's name. Falls back to the id only while it is still loading. */
  name: string
  record: Values | undefined
  isLoading: boolean
  isError: boolean
}) {
  const [open, setOpen] = useState(false)
  // The parent's own stage sections, in its own order. The same prefix rule
  // the record page uses to tell stage sections from Details sections.
  const sections = sectionsFor(module).filter((section) => section.startsWith('STAGE'))
  // Where the parent stopped. Read from ITS module's stage field, never the
  // child's — a Deal reads deal_stage and its Opportunity reads project_stage.
  const stage = record ? stageLabel(stageNumberOf(record[stageFieldOf(module) ?? ''])) : ''

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        {/* The disclosure is the heading, so the whole line is the hit area —
            except the parent's name, which is a link out and stays one. */}
        <CollapsibleTrigger className="group flex items-baseline gap-1.5 text-left text-sm font-semibold">
          {open ? (
            <ChevronDownIcon className="size-3.5 shrink-0 translate-y-0.5" />
          ) : (
            <ChevronRightIcon className="size-3.5 shrink-0 translate-y-0.5" />
          )}
          <span className="group-hover:underline underline-offset-2">{title}</span>
        </CollapsibleTrigger>
        {/* The parent by NAME, as every other lookup on the record reads — the
            id is in the address bar once the link is followed. */}
        <Link className="text-sm underline underline-offset-2" to={`${basePath}/${id}`}>
          {name || id}
        </Link>
        {stage && <span className="text-muted-foreground text-xs">{stage}</span>}
      </div>
      {/* No "open it to change a value": a parent is converted, so it is
          read-only in its own module too. */}
      {open && (
        <p className="text-muted-foreground text-xs">
          Read-only: what the {noun} recorded in its own stages.
        </p>
      )}

      <CollapsibleContent className="space-y-2">
        {isLoading && <p className="text-muted-foreground py-2 text-sm">Loading {noun}…</p>}
        {isError && <p className="py-2 text-sm text-destructive">Could not load this {noun}.</p>}
        {/* No frame of its own — each stage section is already a card, and a
            border around them drew a second, thinner box. */}
        {record && (
          <RecordForm key={`${module}:${id}`} module={module} mode="view" values={record} sections={sections} />
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
