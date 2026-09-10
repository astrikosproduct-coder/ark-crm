import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordListView } from '@/components/list/RecordListView'
import { OpportunityKanbanBoard } from '@/components/opportunities/OpportunityKanbanBoard'
import { opportunityListCell } from '@/components/opportunities/opportunityListCell'
import { RankedOpportunityList } from '@/components/opportunities/RankedOpportunityList'
import { stageKeyOf, stagesFor } from '@/lib/pipeline'
import { PlusIcon } from 'lucide-react'

const ALL = '__all__'

export function OpportunitiesPage() {
  const navigate = useNavigate()
  const [stage, setStage] = useState(ALL)

  // Stage options come from the split range, not from the leads_stage
  // picklist — that picklist still carries all eight of Leads' own keys
  // (0-7), four of which an Opportunity can never hold. See
  // spec/module_split.json's register_corrections.
  const stages = stagesFor('opportunities')

  const filter = useMemo(() => {
    const f: Record<string, string> = {}
    if (stage !== ALL) f.project_stage = stage
    return f
  }, [stage])

  // An Opportunity is meant to arrive by converting a Lead — the conversion
  // flow is the next step, not built yet. The button below exists because the
  // route does; once conversions exist, creating one by hand from here is the
  // exception, not the front door.
  return (
    <PageLayout
      wide
      title="Opportunities"
      subtitle="Stage 4 to 6 of the pipeline. A Lead converts to an Opportunity on leaving Stage 3; an Opportunity converts to a Deal on leaving Stage 6."
      actions={
        <Button onClick={() => navigate('/opportunities/new')}>
          <PlusIcon className="size-4" />
          New opportunity
        </Button>
      }
      tabs={[
        {
          key: 'list',
          label: 'List',
          content: (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2 pt-3">
                <Select value={stage} onValueChange={setStage}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Stage" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>All stages</SelectItem>
                    {stages.map((s) => {
                      const key = stageKeyOf(s.stage)
                      if (!key) return null
                      return (
                        <SelectItem key={s.stage} value={key}>
                          {s.stage} · {s.name}
                        </SelectItem>
                      )
                    })}
                  </SelectContent>
                </Select>
              </div>

              <RecordListView
                module="opportunities"
                collection="opportunities"
                basePath="/opportunities"
                filter={filter}
                renderCell={opportunityListCell}
                pageSize={25}
                emptyMessage="No opportunities yet — convert a Lead at Stage 3 to create one."
              />
            </div>
          ),
        },
        { key: 'pipeline', label: 'Pipeline', content: <OpportunityKanbanBoard /> },
        {
          key: 'low-hanging',
          label: 'Low Hanging',
          content: <RankedOpportunityList flagField="is_low_hanging" rankField="low_hanging_rank" cap={5} />,
        },
        {
          key: 'top-10',
          label: 'Top 10',
          content: <RankedOpportunityList flagField="is_top_10" rankField="top_10_rank" cap={10} />,
        },
      ]}
    />
  )
}
