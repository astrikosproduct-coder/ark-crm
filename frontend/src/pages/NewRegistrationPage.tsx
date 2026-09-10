import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { RecordEditor } from '@/components/record/RecordEditor'
import { ACK_SLA_DAYS, EXCLUSIVITY_DAYS, isoDate, today } from '@/lib/partners'
import { fieldOf, partnerRegistration } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

const MODULE = 'partners'
const COLLECTION = 'registrations'

/**
 * The seven fields a partner supplies when registering a deal.
 *
 * Which seven is spec, not code: partner_registration.capture_fields in
 * spec/extensions.json. The other eight fields of DEAL REGISTRATION —
 * acknowledged date, SLA met, both exclusivity dates, status, extension reason,
 * linked lead — are stamped by ARK on acknowledgement, so offering them here
 * would invite somebody to type an exclusivity window by hand.
 */
export function NewRegistrationPage() {
  const navigate = useNavigate()
  const [search] = useSearchParams()
  const capture = partnerRegistration.capture_fields

  const initialValues = useMemo(() => {
    const values: Values = {
      // The partner submitted it today unless somebody says otherwise. This is
      // what starts the acknowledgement clock.
      submitted_date: isoDate(today()),
    }
    for (const [key, value] of search.entries()) {
      if (fieldOf(MODULE, key)) values[key] = value
    }
    return values
  }, [search])


  return (
    <PageLayout
      title={
        <>
          New deal registration
        </>
      }
      subtitle={`Saving records the claim. It does not start exclusivity — that begins when Astrikos acknowledges, which is due within ${ACK_SLA_DAYS} days and then runs for ${EXCLUSIVITY_DAYS} days inclusive of the start day.`}
      tabs={[
        {
          key: 'new',
          label: 'Registration',
          content: (
            <RecordEditor
              module={MODULE}
              collection={COLLECTION}
              initialValues={initialValues}
              sections={[capture.section]}
              only={capture.fields}
              sectionTitle="REGISTRATION — SUBMITTED BY THE PARTNER"
              // Submitted, not Active: the partner has claimed the deal, and
              // Astrikos has not yet agreed to protect it.
              stamp={{ registration_status: 'SUBMITTED' }}
              saveLabel="Register deal"
              onSaved={(id) => {
                navigate(`/partners/registrations/${id}`, { replace: true })
              }}
              onCancel={() => navigate('/partners')}
            />
          ),
        },
      ]}
    />
  )
}
