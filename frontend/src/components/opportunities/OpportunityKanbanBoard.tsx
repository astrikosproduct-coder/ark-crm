import type { ListRow } from '@/components/list/ListCell'
import { ReadThroughLookup, ReadThroughText } from '@/components/opportunities/opportunityListCell'
import { PipelineKanbanBoard } from '@/components/pipeline/PipelineKanbanBoard'
import { money } from '@/lib/format'
import { carriedListValue } from '@/lib/stageScope'
import { fieldOf } from '@/lib/spec'

const END_CLIENT_TARGET = fieldOf('opportunities', 'end_client')?.lookup_target ?? null

function OpportunityCard({ row }: { row: ListRow }) {
  const value = row.total_value_tcv

  return (
    <>
      <p className="truncate font-medium">
        <ReadThroughText row={row} apiName="opportunity_name" />
      </p>
      <p className="truncate text-xs text-muted-foreground">
        <ReadThroughLookup row={row} apiName="end_client" lookupTarget={END_CLIENT_TARGET} />
      </p>
      <div className="mt-1.5 flex items-center justify-between text-xs">
        <span className="tabular-nums">{typeof value === 'number' ? `$${money(value)}` : '—'}</span>
        <span className="tabular-nums text-muted-foreground">
          {typeof row.probability_pct === 'number' ? `${row.probability_pct}%` : '—'}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
        <span className="truncate">
          {typeof row.submission_deadline === 'string' && row.submission_deadline ? row.submission_deadline : '—'}
        </span>
        <span className="tabular-nums">
          {/* Progression is editable per stage now, so a record with none of
              its own falls back to the positional default — see stageScope. */}
          {(() => {
            const p = carriedListValue('opportunities', 'progression_pct', row)
            return typeof p === 'number' ? `${p}% through` : '—'
          })()}
        </span>
      </div>
    </>
  )
}

/**
 * Pipeline view for Opportunities (Stage 4-6), same shape as LeadKanbanBoard.
 * opportunity_name and end_client are read-through — see opportunityListCell
 * — so the card resolves them per row the same way the List tab does, rather
 * than reading them off the row directly.
 */
export function OpportunityKanbanBoard() {
  return (
    <PipelineKanbanBoard
      module="opportunities"
      collection="opportunities"
      basePath="/opportunities"
      stageValueOf={(row) => row.project_stage}
      noun="opportunity"
      nounPlural="opportunities"
      renderCard={(row) => <OpportunityCard row={row} />}
    />
  )
}
