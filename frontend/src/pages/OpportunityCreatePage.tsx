import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { RecordEditor } from '@/components/record/RecordEditor'
import { UnsavedBadge } from '@/components/record/UnsavedBadge'
import { NEW_RECORD_ID } from '@/hooks/useRecordForm'
import {
  CURRENT_USER_ID,
  probabilityMidpoint,
  sectionForStage,
  stageKeyOf,
  stagesFor,
} from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'
import { useDiscardToken } from '@/store/useDraftStore'

const MODULE = 'opportunities'
const COLLECTION = 'opportunities'

/**
 * The real front door is converting a Lead at Stage 3 — this page exists
 * because the route does, for the same reason LeadsPage links to it, and
 * because a spec-driven prototype should let a reviewer poke at every module
 * even before the workflow that is meant to populate it is built.
 *
 * It cannot set identity. End Client, Customer (Partner / SI), Segment and the
 * rest are read_through fields — resolved from parent_lead, never stored here
 * — and this record has no parent_lead until a real conversion gives it one.
 * A hand-created Opportunity is therefore identity-less until that happens,
 * which the form makes visible rather than hiding: every read-through field
 * renders "Not resolved — no Parent Lead is set on this record."
 */
export function OpportunityCreatePage() {
  const navigate = useNavigate()
  const firstStage = stagesFor(MODULE)[0]?.stage ?? 4
  const section = sectionForStage(MODULE, firstStage)
  const discardToken = useDiscardToken(MODULE, NEW_RECORD_ID)

  const initialValues = useMemo<Values>(
    () => ({
      project_stage: stageKeyOf(firstStage),
      probability_pct: probabilityMidpoint(firstStage),
    }),
    [firstStage]
  )

  return (
    <PageLayout
      title={
        <>
          New opportunity
          <UnsavedBadge module={MODULE} recordId={NEW_RECORD_ID} />
        </>
      }
      subtitle={`Stage ${firstStage} — normally reached by converting a Lead, not created directly.`}
      tabs={[
        {
          key: 'new',
          label: 'Details',
          content: (
            <RecordEditor
              key={discardToken}
              module={MODULE}
              collection={COLLECTION}
              initialValues={initialValues}
              sections={section ? [section] : undefined}
              saveLabel="Create opportunity"
              stamp={{
                created_date: new Date().toISOString(),
                created_by: CURRENT_USER_ID,
                modified_date: new Date().toISOString(),
                modified_by: CURRENT_USER_ID,
              }}
              onSaved={(id) => navigate(`/opportunities/${id}`, { replace: true })}
              onCancel={() => navigate('/opportunities')}
            />
          ),
        },
      ]}
    />
  )
}
