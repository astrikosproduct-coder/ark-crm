import { useMemo, useState } from 'react'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordListView } from '@/components/list/RecordListView'
import { DealKanbanBoard } from '@/components/deals/DealKanbanBoard'
import { dealListCell } from '@/components/deals/dealListCell'
import { fieldOf, optionsFor } from '@/lib/spec'

const ALL = '__all__'

export function DealsPage() {
  const [stage, setStage] = useState(ALL)
  const stageField = fieldOf('deals', 'deal_stage')

  const filter = useMemo(() => {
    const f: Record<string, string> = {}
    if (stage !== ALL) f.deal_stage = stage
    return f
  }, [stage])

  return (
    <PageLayout
      wide
      title="Deals"
      subtitle="Stage 7 to 9 of the pipeline. A Deal is created when a Lead converts at Stage 7."
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
                    {optionsFor(stageField?.picklist).map((o) => (
                      <SelectItem key={o.key} value={o.key}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <RecordListView
                module="deals"
                collection="deals"
                basePath="/deals"
                filter={filter}
                renderCell={dealListCell}
                pageSize={25}
                emptyMessage="No deals yet — convert a Lead at Stage 7 to create one."
              />
            </div>
          ),
        },
        { key: 'pipeline', label: 'Pipeline', content: <DealKanbanBoard /> },
      ]}
    />
  )
}
