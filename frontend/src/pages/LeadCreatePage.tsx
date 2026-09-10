import { currentUserId } from '@/lib/currentUser'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { LeadAccountFieldSync, backfillAccountFieldsFromLead } from '@/components/leads/LeadAccountFieldSync'
import { RecordEditor } from '@/components/record/RecordEditor'
import { probabilityMidpoint, sectionForStage, stageKeyOf } from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'

const MODULE = 'leads'
const COLLECTION = 'leads'

/**
 * A new Lead starts at Stage 0 — Connect and nowhere else. The other seven
 * stages' fields fill in as the lead is advanced, one stage at a time, from
 * its own detail page — not offered up front, which is what letting
 * RecordCreatePage render every section of a 120-field module would do.
 */
/** A lead opens at Stage 0. Module-level so it is one stable object. */
const CREATE_STAGE = { stage: 0, currentStage: 0 }

export function LeadCreatePage() {
  const navigate = useNavigate()
  const section = sectionForStage(MODULE, 0)

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
        </>
      }
      subtitle="Stage 0 — Connect. Later stages fill in as the lead advances."
      tabs={[
        {
          key: 'new',
          label: 'Connect',
          content: (
            <RecordEditor
              module={MODULE}
              collection={COLLECTION}
              initialValues={initialValues}
              sections={section ? [section] : undefined}
              // A lead is created AT Stage 0, so a per-stage answer given on
              // this form belongs to Stage 0. Without this the inline On Hold
              // Reason would write the plain api_name here and the record page
              // — which reads the per-stage key — would show nothing.
              stageScope={CREATE_STAGE}
              sideEffects={<LeadAccountFieldSync />}
              afterSave={backfillAccountFieldsFromLead}
              saveLabel="Create lead"
              stamp={{
                created_date: new Date().toISOString(),
                created_by: currentUserId(),
                modified_date: new Date().toISOString(),
                modified_by: currentUserId(),
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
