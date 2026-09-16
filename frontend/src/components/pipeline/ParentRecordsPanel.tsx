import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { RecordForm } from '@/components/form/RecordForm'
import type { PipelineRecordContext } from '@/components/pipeline/types'
import { api } from '@/lib/api'
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
 */
export function ParentRecordsPanel({ ctx }: { ctx: PipelineRecordContext }) {
  const { module, opportunityId, opportunity, leadId, lead } = useLineage(ctx)

  if (module === 'leads' || !ctx.values) return null

  return (
    <div className="space-y-8">
      {module === 'deals' &&
        (opportunityId ? (
          <ParentSection
            title="Read through Parent Opportunity"
            module="opportunities"
            basePath="/opportunities"
            noun="opportunity"
            id={opportunityId}
            record={opportunity.data}
            isLoading={opportunity.isLoading}
            isError={opportunity.isError}
          />
        ) : (
          <section className="space-y-1">
            <h3 className="text-sm font-semibold">Read through Parent Opportunity</h3>
            <p className="text-muted-foreground text-sm">
              {leadId
                ? `This Deal was made directly from ${leadId} — a paid POC / pilot — so there is no Opportunity stage to show.`
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
  record,
  isLoading,
  isError,
}: {
  title: string
  module: string
  basePath: string
  noun: string
  id: string
  record: Values | undefined
  isLoading: boolean
  isError: boolean
}) {
  // The parent's own stage sections, in its own order. The same prefix rule
  // the record page uses to tell stage sections from Details sections.
  const sections = sectionsFor(module).filter((section) => section.startsWith('STAGE'))

  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold">
          {title} —{' '}
          <Link className="underline underline-offset-2" to={`${basePath}/${id}`}>
            {id}
          </Link>
        </h3>
        {record && <span className="text-muted-foreground text-xs">{displayNameOf(record)}</span>}
      </div>
      {/* No "open it to change a value": a parent is converted, so it is
          read-only in its own module too. */}
      <p className="text-muted-foreground text-xs">
        Read-only: what the {noun} recorded in its own stages.
      </p>

      {isLoading && <p className="text-muted-foreground py-2 text-sm">Loading {id}…</p>}
      {isError && <p className="py-2 text-sm text-destructive">Could not load {id}.</p>}
      {/* No frame of its own — each stage section is already a card, and a
          border around them drew a second, thinner box. */}
      {record && (
        <RecordForm key={`${module}:${id}`} module={module} mode="view" values={record} sections={sections} />
      )}
    </section>
  )
}
