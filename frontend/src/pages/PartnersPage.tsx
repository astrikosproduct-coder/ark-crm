import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ListPageLayout } from '@/components/layout/ListPageLayout'
import { ListFilterBar } from '@/components/list/ListFilterBar'
import { ModuleActions } from '@/components/list/ModuleActions'
import { RecordListView } from '@/components/list/RecordListView'
import { registrationListCell } from '@/components/partners/registrationListCell'
import { useListFilters } from '@/lib/listFilters'
import { partnerAccountTypes } from '@/lib/spec'

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
  // Two lists on one page, so each keeps its own filters: registration keys carry
  // an "r." prefix in the URL. A registration is its own module (metadata v2,
  // 24 Sep 2026); a partner record is an account.
  const registrationFilters = useListFilters({
    view: 'registrations',
    fieldModule: 'registrations',
    prefix: 'r.',
  })
  const partnerFilters = useListFilters({
    view: 'partners',
    fieldModule: 'accounts',
    choiceLimits: { account_type: partnerAccountTypes },
  })
  const registrationFilter = useMemo(() => registrationFilters.params(), [registrationFilters])
  const partnerFilter = useMemo(
    // Picking partner types narrows the roster; nothing here can widen it past partners.
    () => ({ account_type: partnerAccountTypes, ...partnerFilters.params() }),
    [partnerFilters]
  )

  return (
    <ListPageLayout
      pageKey="partners"
      title="Partners"
      actions={
        // One split button, as Leads and Accounts: New Registration, and ▾ for
        // Import / Export — which are the partner RECORDS, accounts with a
        // partner type. Registrations are created one at a time, with their checks.
        <ModuleActions
          module="partners"
          plural="Partners"
          noun="partner"
          createLabel="New Registration"
          onCreate={() => navigate('/partners/registrations/new')}
          exportFilter={() => partnerFilters.params()}
        />
      }
      views={[
        {
          key: 'registrations',
          label: 'Registrations',
          toolbar: (
            <ListFilterBar filters={registrationFilters} plural="Registrations" searchPlaceholder="Search project, partner or client…" />
          ),
          content: (
            <div className="flex min-h-0 flex-1 flex-col">
              <RecordListView
                fill
                module="registrations"
                columnChoices={[...registrationFilters.common, ...registrationFilters.others].map((f) => f.field)}
                collection="registrations"
                basePath="/partners/registrations"
                filter={registrationFilter}
                hideSearch
                renderCell={registrationListCell}
                emptyMessage="No deal registrations yet."
              />
            </div>
          ),
        },
        {
          key: 'partners',
          label: 'Partner records',
          toolbar: <ListFilterBar filters={partnerFilters} plural="Partners" searchPlaceholder="Search name, region or segment…" />,
          content: (
            <div className="flex min-h-0 flex-1 flex-col">
              <RecordListView
                fill
                module="partners"
                columnChoices={[...partnerFilters.common, ...partnerFilters.others].map((f) => f.field)}
                collection="accounts"
                basePath="/partners"
                filter={partnerFilter}
                hideSearch
                emptyMessage="No account carries a partner type yet."
              />
            </div>
          ),
        },
      ]}
    />
  )
}
