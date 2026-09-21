import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { PageLayout } from '@/components/layout/PageLayout'
import { RecordEditor } from '@/components/record/RecordEditor'
import { isoDate, today } from '@/lib/partners'
import { fieldAt, partnerRegistration } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'

const MODULE = 'partners'
const COLLECTION = 'registrations'

/**
 * The eight fields a partner supplies when registering a deal.
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
      // USD until the user picks another, as on a new Lead.
      currency: 'USD',
    }
    // fieldAt, not fieldOf: `partner` is defined in two sections of the
    // Partners register, so fieldOf returns nothing for it and the partner a
    // partner's own page hands over (?partner=ACC-…) was silently dropped.
    for (const [key, value] of search.entries()) {
      if (fieldAt(MODULE, capture.section, key)) values[key] = value
    }
    return values
  }, [search, capture.section])


  return (
    <PageLayout
      title={
        <>
          New deal registration
        </>
      }
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
              // No sectionTitle: the header is the register's own section name,
              // DEAL REGISTRATION, the same one Administration and the saved
              // record show. A heading that exists nowhere else read as a
              // second, different form.
              // Submitted, not Active: the partner has claimed the deal, and
              // Astrikos has not yet agreed to protect it.
              stamp={{ registration_status: 'SUBMITTED' }}
              saveLabel="Register deal"
              onSaved={(id, record) => {
                // A save that raised a conflict lands on it — that is the next
                // thing somebody has to do.
                const raised = Array.isArray(record.raised_conflicts) && record.raised_conflicts.length > 0
                navigate(`/partners/registrations/${id}${raised ? '?tab=conflict' : ''}`, { replace: true })
              }}
              onCancel={() => navigate('/partners')}
            />
          ),
        },
      ]}
    />
  )
}
