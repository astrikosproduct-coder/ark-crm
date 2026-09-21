import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { LeadAccountFieldSync, backfillAccountFieldsFromLead } from '@/components/leads/LeadAccountFieldSync'
import { RecordEditor } from '@/components/record/RecordEditor'
import { STAGE_PCT_FIELDS, createFormSections, stageKeyOf, stagesFor } from '@/lib/pipeline'
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
  // The same sections, in the same order, as the Stage 0 tab of the record
  // this becomes: Health & Forecast first, then Connect (21 Sep 2026). The
  // two percentages are hidden — the server sets them from the stage.
  const sections = useMemo(() => createFormSections(MODULE, 0), [])
  const stage = stagesFor(MODULE)[0]

  /**
   * The three RECORD STATE fields, seeded rather than asked for.
   *
   * All three used to sit in `STAGE 0 — CONNECT` and render on this form;
   * they moved to Leads' own RECORD STATE section so that changing the status
   * of a Stage 1 lead no longer means clicking back to the Stage 0 tab. This
   * page renders one section — sectionForStage(leads, 0) — so they are not on
   * it any more, and `lead_status` is Mandatory: without a value here the
   * form would refuse to save a field it never showed.
   *
   * Seeding is the right answer rather than a workaround. A lead being
   * created is Open, at Stage 0, by definition — there is no second option to
   * offer, and the page's own subtitle already says which stage this is. The
   * status becomes editable the moment the record exists, on its Details tab.
   */
  const initialValues = useMemo<Values>(
    () => ({
      project_stage: stageKeyOf(0),
      lead_status: 'OPEN',
      // Defaults the user can change (14 Sep 2026). The server applies the
      // same three to a lead created any other way — from a registration, or
      // an expansion off a Deal — see create_lead in app/routers/leads.py.
      currency: 'USD',
      is_primary_pursuit: true,
      // Probability %/Progression % are NOT seeded here — the server gives
      // the Lead its stage's pair when it is created (app/progression.py).
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
      subtitle={stage ? `Stage ${stage.stage} — ${stage.name}` : undefined}
      tabs={[
        {
          key: 'new',
          label: 'Current stage',
          content: (
            <RecordEditor
              module={MODULE}
              collection={COLLECTION}
              initialValues={initialValues}
              sections={sections.length ? sections : undefined}
              hiddenFields={STAGE_PCT_FIELDS}
              // A lead is created AT Stage 0, so a per-stage answer given on
              // this form belongs to Stage 0. Without this the inline On Hold
              // Reason would write the plain api_name here and the record page
              // — which reads the per-stage key — would show nothing.
              stageScope={CREATE_STAGE}
              sideEffects={<LeadAccountFieldSync />}
              afterSave={backfillAccountFieldsFromLead}
              saveLabel="Create lead"
              stamp={{
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
