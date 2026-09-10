import { currentUserId } from '@/lib/currentUser'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { RecordEditor } from '@/components/record/RecordEditor'
import {
  probabilityMidpoint,
  sectionForStage,
  stageKeyOf,
  stagesFor,
} from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'

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

  const initialValues = useMemo<Values>(
    () => ({
      project_stage: stageKeyOf(firstStage),
      probability_pct: probabilityMidpoint(firstStage),
    }),
    [firstStage]
  )

  // The record is created AT this stage, so a per-stage answer given on this
  // form belongs to it — see the same note on LeadCreatePage.
  const stageScope = useMemo(
    () => ({ stage: firstStage, currentStage: firstStage }),
    [firstStage]
  )

  return (
    <PageLayout
      title={
        <>
          New opportunity
        </>
      }
      subtitle={`Stage ${firstStage} — normally reached by converting a Lead, not created directly.`}
      tabs={[
        {
          key: 'new',
          label: 'Details',
          content: (
            <RecordEditor
              module={MODULE}
              collection={COLLECTION}
              initialValues={initialValues}
              sections={section ? [section] : undefined}
              stageScope={stageScope}
              saveLabel="Create opportunity"
              stamp={{
                created_date: new Date().toISOString(),
                created_by: currentUserId(),
                modified_date: new Date().toISOString(),
                modified_by: currentUserId(),
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
