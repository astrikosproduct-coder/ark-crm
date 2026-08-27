import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { LeadAccountFieldSync, backfillAccountFieldsFromLead } from '@/components/leads/LeadAccountFieldSync'
import { RecordEditor } from '@/components/record/RecordEditor'
import { UnsavedBadge } from '@/components/record/UnsavedBadge'
import { NEW_RECORD_ID } from '@/hooks/useRecordForm'
import { CURRENT_USER_ID, probabilityMidpoint, sectionForStage, stageKeyOf } from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'
import { useDiscardToken } from '@/store/useDraftStore'

const MODULE = 'leads'
const COLLECTION = 'leads'

/**
 * A new Lead starts at Stage 0 — Connect and nowhere else. The other seven
 * stages' fields fill in as the lead is advanced, one stage at a time, from
 * its own detail page — not offered up front, which is what letting
 * RecordCreatePage render every section of a 120-field module would do.
 */
export function LeadCreatePage() {
  const navigate = useNavigate()
  const section = sectionForStage(MODULE, 0)
  const discardToken = useDiscardToken(MODULE, NEW_RECORD_ID)

  const initialValues = useMemo<Values>(
    () => ({
      project_stage: stageKeyOf(0),
      probability_pct: probabilityMidpoint(0),
    }),
    []
  )

  return (
    <PageLayout
      title={
        <>
          New lead
          <UnsavedBadge module={MODULE} recordId={NEW_RECORD_ID} />
        </>
      }
      subtitle="Stage 0 — Connect. Later stages fill in as the lead advances."
      tabs={[
        {
          key: 'new',
          label: 'Connect',
          content: (
            <RecordEditor
              key={discardToken}
              module={MODULE}
              collection={COLLECTION}
              initialValues={initialValues}
              sections={section ? [section] : undefined}
              sideEffects={<LeadAccountFieldSync />}
              afterSave={backfillAccountFieldsFromLead}
              saveLabel="Create lead"
              stamp={{
                created_date: new Date().toISOString(),
                created_by: CURRENT_USER_ID,
                modified_date: new Date().toISOString(),
                modified_by: CURRENT_USER_ID,
              }}
              onSaved={(id) => navigate(`/leads/${id}`, { replace: true })}
              onCancel={() => navigate('/leads')}
            />
          ),
        },
      ]}
    />
  )
}
