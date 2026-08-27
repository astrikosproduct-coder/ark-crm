import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { AccountDetailPage } from '@/pages/AccountDetailPage'
import { AccountsPage } from '@/pages/AccountsPage'
import { ContactDetailPage } from '@/pages/ContactDetailPage'
import { ContactsPage } from '@/pages/ContactsPage'
import { DealDetailPage } from '@/pages/DealDetailPage'
import { DealsPage } from '@/pages/DealsPage'
import { FormEnginePage } from '@/pages/FormEnginePage'
import { LeadCreatePage } from '@/pages/LeadCreatePage'
import { LeadDetailPage } from '@/pages/LeadDetailPage'
import { LeadsPage } from '@/pages/LeadsPage'
import { ModuleDetailPage } from '@/pages/ModuleDetailPage'
import { ModulePage } from '@/pages/ModulePage'
import { NewRegistrationPage } from '@/pages/NewRegistrationPage'
import { OpportunityCreatePage } from '@/pages/OpportunityCreatePage'
import { OpportunityDetailPage } from '@/pages/OpportunityDetailPage'
import { OpportunitiesPage } from '@/pages/OpportunitiesPage'
import { PartnerDetailPage } from '@/pages/PartnerDetailPage'
import { PartnersPage } from '@/pages/PartnersPage'
import { RegistrationDetailPage } from '@/pages/RegistrationDetailPage'
import { RecordCreatePage } from '@/pages/RecordCreatePage'
import { SettingsPage } from '@/pages/SettingsPage'
import { SpecHealthPage } from '@/pages/SpecHealthPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="form-engine" element={<FormEnginePage />} />
          <Route path="spec-health" element={<SpecHealthPage />} />
          <Route path="settings" element={<SettingsPage />} />

          <Route path="leads" element={<LeadsPage />} />
          <Route path="leads/new" element={<LeadCreatePage />} />
          <Route path="leads/:id" element={<LeadDetailPage />} />

          <Route path="opportunities" element={<OpportunitiesPage />} />
          <Route path="opportunities/new" element={<OpportunityCreatePage />} />
          <Route path="opportunities/:id" element={<OpportunityDetailPage />} />

          <Route path="deals" element={<DealsPage />} />
          <Route path="deals/:id" element={<DealDetailPage />} />

          <Route path="accounts" element={<AccountsPage />} />
          <Route
            path="accounts/new"
            element={
              <RecordCreatePage
                module="accounts"
                collection="accounts"
                basePath="/accounts"
                title="New account"
              />
            }
          />
          <Route path="accounts/:id" element={<AccountDetailPage />} />

          <Route path="contacts" element={<ContactsPage />} />
          <Route
            path="contacts/new"
            element={
              <RecordCreatePage
                module="contacts"
                collection="contacts"
                basePath="/contacts"
                title="New contact"
              />
            }
          />
          <Route path="contacts/:id" element={<ContactDetailPage />} />

          {/* Registrations are nested under partners rather than given a
              top-level route, because a registration has no meaning apart from
              the partner that submitted it. The static segments outrank
              partners/:id, so REG ids and ACC ids cannot collide. */}
          <Route path="partners" element={<PartnersPage />} />
          <Route path="partners/registrations/new" element={<NewRegistrationPage />} />
          <Route path="partners/registrations/:id" element={<RegistrationDetailPage />} />
          <Route path="partners/:id" element={<PartnerDetailPage />} />

          {/* Everything not built yet still resolves, through the generic
              spec-driven screens. */}
          <Route path=":module" element={<ModulePage />} />
          <Route path=":module/:id" element={<ModuleDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
