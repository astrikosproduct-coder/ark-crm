import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordListView } from '@/components/list/RecordListView'
import { LeadKanbanBoard } from '@/components/leads/LeadKanbanBoard'
import { leadListCell } from '@/components/leads/leadListCell'
import { api } from '@/lib/api'
import { stageKeyOf, stagesFor } from '@/lib/pipeline'
import { displayNameOf, fieldOf, idOf, optionsFor } from '@/lib/spec'
import { applyLookupFilter } from '@/lib/spec/conditions'

const ALL = '__all__'

export function LeadsPage() {
  const navigate = useNavigate()
  const [stage, setStage] = useState(ALL)
  const [owner, setOwner] = useState(ALL)
  const [status, setStatus] = useState(ALL)

  // Stage options come from the split range, not from the leads_stage
  // picklist — that picklist still carries all eight of the pre-split keys
  // (0-7), four of which a Lead can no longer reach. Same rule as
  // OpportunitiesPage. See spec/module_split.json's register_corrections.
  const stages = stagesFor('leads')
  const statusField = fieldOf('leads', 'lead_status')
  const ownerField = fieldOf('leads', 'bd_owner')

  const { data: users } = useQuery({
    queryKey: ['collection', 'users'],
    queryFn: async () => (await api.get<Record<string, unknown>[]>('/users')).data,
  })
  const owners = useMemo(
    () => applyLookupFilter(users ?? [], ownerField?.lookup_filter_expr),
    [users, ownerField]
  )

  const filter = useMemo(() => {
    const f: Record<string, string> = {}
    if (stage !== ALL) f.project_stage = stage
    if (owner !== ALL) f.bd_owner = owner
    if (status !== ALL) f.lead_status = status
    return f
  }, [stage, owner, status])

  return (
    <PageLayout
      wide
      title="Leads"
      subtitle="Stage 0 to 3 of the pipeline. A Lead moves to Opportunities at Stage 3."
      actions={
        <Button onClick={() => navigate('/leads/new')}>
          <PlusIcon className="size-4" />
          New lead
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

                <Select value={owner} onValueChange={setOwner}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Owner" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>All owners</SelectItem>
                    {owners.map((u) => (
                      <SelectItem key={idOf(u)} value={idOf(u)}>
                        {displayNameOf(u)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select value={status} onValueChange={setStatus}>
                  <SelectTrigger className="w-48">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>All statuses</SelectItem>
                    {optionsFor(statusField?.picklist).map((o) => (
                      <SelectItem key={o.key} value={o.key}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <RecordListView
                module="leads"
                collection="leads"
                basePath="/leads"
                filter={filter}
                renderCell={leadListCell}
                pageSize={25}
                emptyMessage="No leads yet."
              />
            </div>
          ),
        },
        { key: 'pipeline', label: 'Pipeline', content: <LeadKanbanBoard /> },
      ]}
    />
  )
}
