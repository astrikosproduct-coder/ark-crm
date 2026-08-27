import { useNavigate } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { RecordListView } from '@/components/list/RecordListView'
import { registrationListCell } from '@/components/partners/registrationListCell'
import { EXCLUSIVITY_DAYS } from '@/lib/partners'
import { labelForValue, partnerAccountTypes } from '@/lib/spec'

/**
 * Partners.
 *
 * Registrations lead, because the registration is the front door: a partner
 * brings a deal before anybody edits a partner profile. Partner records are the
 * second tab and are a VIEW OVER ACCOUNTS — a partner is an account whose
 * account_type includes a partner type, never a second organisation record. e&
 * Enterprise appears here and on the Accounts screen as one and the same row.
 */
export function PartnersPage() {
  const navigate = useNavigate()

  const rosterNames = partnerAccountTypes
    .map((t) => labelForValue('accounts__account_type', t))
    .join(' and ')

  return (
    <PageLayout
      wide
      title="Partners"
      subtitle="Deal registrations and the partner organisations behind them."
      actions={
        <Button onClick={() => navigate('/partners/registrations/new')}>
          <PlusIcon className="size-4" />
          New Registration
        </Button>
      }
      tabs={[
        {
          key: 'registrations',
          label: 'Registrations',
          content: (
            <div className="space-y-3 py-3">
              <p className="text-sm text-muted-foreground">
                A registration grants the partner exclusivity on one client and one project,
                running {EXCLUSIVITY_DAYS} days from the day Astrikos acknowledges it, that day
                included.
              </p>
              <RecordListView
                module="registrations"
                collection="registrations"
                basePath="/partners/registrations"
                renderCell={registrationListCell}
                emptyMessage="No deal registrations yet."
              />
            </div>
          ),
        },
        {
          key: 'partners',
          label: 'Partner records',
          content: (
            <div className="space-y-3 py-3">
              <p className="text-sm text-muted-foreground">
                Accounts whose Account Type includes {rosterNames}. These are the same records as
                on the Accounts screen — one organisation, one row, seen from the partner side.
              </p>
              <RecordListView
                module="partners"
                collection="accounts"
                basePath="/partners"
                filter={{ account_type: partnerAccountTypes }}
                emptyMessage="No account carries a partner type yet."
              />
            </div>
          ),
        },
      ]}
    />
  )
}
